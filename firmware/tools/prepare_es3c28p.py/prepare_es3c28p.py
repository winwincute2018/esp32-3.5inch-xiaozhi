from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def replace_once(path, old, new):
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"Expected one match in {path.name}, got {count}: {old[:80]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")

ini = ROOT / "platformio.ini"
text = ini.read_text(encoding="utf-8")
replacements = {
    "board = esp32dev": "board = esp32s3\nboard_build.flash_size = 16MB\nboard_build.arduino.memory_type = qio_opi\nboard_build.f_flash = 40000000L\nboard_build.flash_mode = dio\nboard_build.partitions = partitions_es3c28p.csv",
    "board_build.partitions = huge_app.csv": "",
    "-DST7796_DRIVER=1": "-DILI9341_DRIVER=1",
    "-DTFT_WIDTH=320": "-DTFT_WIDTH=240",
    "-DTFT_HEIGHT=480": "-DTFT_HEIGHT=320",
    "-DTFT_MISO=12": "-DTFT_MISO=13",
    "-DTFT_MOSI=13": "-DTFT_MOSI=11",
    "-DTFT_SCLK=14": "-DTFT_SCLK=12",
    "-DTFT_CS=15": "-DTFT_CS=10",
    "-DTFT_DC=2": "-DTFT_DC=46",
    "-DTFT_BL=27": "-DTFT_BL=45",
    "-DSPI_FREQUENCY=80000000": "-DSPI_FREQUENCY=40000000",
    "-DTOUCH_CS=33": "-DTOUCH_CS=-1",
    "\t-DSPI_TOUCH_FREQUENCY=2500000\n": "",
    "\t-DSMOOTH_FONT=0": "\t-DBOARD_HAS_PSRAM\n\t-DTFT_INVERSION_ON\n\t-DSMOOTH_FONT=0",
}
for old, new in replacements.items():
    if old not in text:
        raise SystemExit(f"Missing PlatformIO setting: {old!r}")
    text = text.replace(old, new, 1)
text = text.replace("board_build.partitions = huge_app.csv\n", "", 1)
if "board_build.partitions = partitions_es3c28p.csv" not in text:
    raise SystemExit("Missing ES3C28P partition setting")
ini.write_text(text, encoding="utf-8")

(ROOT / "partitions_es3c28p.csv").write_text(
    "# Name, Type, SubType, Offset, Size, Flags\n"
    "nvs, data, nvs, 0x9000, 0x5000,\n"
    "otadata, data, ota, 0xe000, 0x2000,\n"
    "phy_init, data, phy, 0xf000, 0x1000,\n"
    "factory, app, factory, 0x10000, 0x700000,\n"
    "storage, data, spiffs, 0x710000, 0x8F0000,\n",
    encoding="utf-8",
)

main = ROOT / "src" / "main.cpp"
replace_once(main, "#include <SD.h>\n", "#include <SD.h>\n#include <SD_MMC.h>\n#define SD SD_MMC\n")
replace_once(main, "static const int PIN_BL = 27;", "static const int PIN_BL = 45;")
replace_once(main, "static SPIClass sdSPI(VSPI);  // TF slot: CS5 SCK18 MISO19 MOSI23 (VSPI's native pins; HSPI drives the display)\n", "")
replace_once(main, "  tft.setRotation(1);\n", "  tft.setRotation(1);\n  tft.invertDisplay(true);\n")
replace_once(main, "  sdSPI.begin(18, 19, 23, 5);", "  SD_MMC.setPins(38, 40, 39, 41, 48, 47);")
replace_once(main, '  sdOk = SD.begin(5, sdSPI, 10000000, "/sd", 3);', '  sdOk = SD_MMC.begin("/sd", false, false, 10000, 3);')
text = main.read_text(encoding="utf-8")
start = text.index("static void dispFlush(")
end = text.index("\nstatic uint8_t blLevel", start)
flush = r'''static void dispFlush(lv_disp_drv_t *drv, const lv_area_t *a, lv_color_t *c) {
  // Render the original 480x320 UI into the ES3C28P's 320x240 landscape panel.
  static uint16_t row[320];
  const int srcW = a->x2 - a->x1 + 1;
  const int dx0 = max(0, a->x1 * 2 / 3);
  const int dxEnd = min(320, ((a->x2 + 1) * 2 + 2) / 3);
  const int dy0 = max(0, a->y1 * 3 / 4);
  const int dyEnd = min(240, ((a->y2 + 1) * 3 + 3) / 4);
  const int outW = dxEnd - dx0;
  if (outW > 0) {
    tft.startWrite();
    for (int dy = dy0; dy < dyEnd; ++dy) {
      int sy = min(319, dy * 4 / 3);
      sy = constrain(sy, a->y1, a->y2);
      for (int dx = dx0; dx < dxEnd; ++dx) {
        int sx = min(479, dx * 3 / 2);
        sx = constrain(sx, a->x1, a->x2);
        uint16_t px = c[(sy - a->y1) * srcW + (sx - a->x1)].full;
        row[dx - dx0] = __builtin_bswap16(px);
      }
      tft.setAddrWindow(dx0, dy, outW, 1);
      tft.pushColors(row, outW, true);
    }
    tft.endWrite();
  }
  lv_disp_flush_ready(drv);
}'''
main.write_text(text[:start] + flush + text[end:], encoding="utf-8")

touch = r'''#pragma once
#include <Arduino.h>
#include <Wire.h>
#include <lvgl.h>

// FT6336G capacitive controller on ES3C28P, I2C address 0x38.
static const uint8_t FT6336_ADDR = 0x38;
static const int TOUCH_SDA = 16, TOUCH_SCL = 15, TOUCH_RST = 18, TOUCH_INT = 17;
static volatile bool gTouchSwallow = false, gTouchWake = false;
static volatile uint32_t gTouchPresses = 0;
static uint32_t fakeStart = 0, fakeDur = 0;
static int fakeX1, fakeY1, fakeX2, fakeY2;

static void xptInit() {
  pinMode(TOUCH_RST, OUTPUT);
  digitalWrite(TOUCH_RST, LOW);
  delay(10);
  digitalWrite(TOUCH_RST, HIGH);
  pinMode(TOUCH_INT, INPUT_PULLUP);
  Wire.begin(TOUCH_SDA, TOUCH_SCL, 400000);
  delay(100);
}

// Return touch coordinates in landscape panel space (320x240).
static bool xptSample(int &x, int &y) {
  Wire.beginTransmission(FT6336_ADDR);
  Wire.write(0x02);
  if (Wire.endTransmission(false) != 0 || Wire.requestFrom(FT6336_ADDR, (uint8_t)5) != 5) return false;
  uint8_t count = Wire.read() & 0x0F;
  uint8_t xh = Wire.read(), xl = Wire.read(), yh = Wire.read(), yl = Wire.read();
  if (count == 0) return false;
  int rawX = ((xh & 0x0F) << 8) | xl;
  int rawY = ((yh & 0x0F) << 8) | yl;
  if (rawX >= 240 || rawY >= 320) return false;
  x = 319 - rawY;
  y = rawX;
  return true;
}

static void touchInject(int x1, int y1, int x2, int y2, uint32_t dur) {
  fakeX1 = x1; fakeY1 = y1; fakeX2 = x2; fakeY2 = y2;
  fakeDur = dur < 60 ? 60 : dur;
  fakeStart = millis();
}

static void touchRead(lv_indev_drv_t *, lv_indev_data_t *data) {
  static int16_t px = 0, py = 0;
  static bool down = false;
  int x, y;
  if (gTouchSwallow) {
    static uint32_t lastPress = 0;
    if (xptSample(x, y)) { gTouchWake = true; lastPress = millis(); }
    else if (lastPress && millis() - lastPress > 150) { gTouchSwallow = false; lastPress = 0; }
    data->state = LV_INDEV_STATE_REL;
    return;
  }
  if (fakeDur) {
    uint32_t elapsed = millis() - fakeStart;
    float t = elapsed >= fakeDur ? 1.0f : (float)elapsed / fakeDur;
    data->point.x = fakeX1 + (int)((fakeX2 - fakeX1) * t);
    data->point.y = fakeY1 + (int)((fakeY2 - fakeY1) * t);
    data->state = elapsed >= fakeDur ? LV_INDEV_STATE_REL : LV_INDEV_STATE_PR;
    if (elapsed >= fakeDur) fakeDur = 0;
    return;
  }
  if (xptSample(x, y)) {
    px = constrain(map(x, 0, 319, 0, 479), 0, 479);
    py = constrain(map(y, 0, 239, 0, 319), 0, 319);
    if (!down) ++gTouchPresses;
    down = true;
  } else {
    down = false;
  }
  data->point.x = px;
  data->point.y = py;
  data->state = down ? LV_INDEV_STATE_PR : LV_INDEV_STATE_REL;
}

static bool touchLoadCal() { return true; }
static void touchCalibrate() {}
'''
(ROOT / "src" / "touch.h").write_text(touch, encoding="utf-8")

config = ROOT / "src" / "config.h"
replace_once(config, "static bool appInLauncher(int id) { return id != 0 && id != 4 && id != 5 && id != 7; }", "static bool appInLauncher(int id) { return id != 0 && id != 4 && id != 5 && id != 7 && id != 9; }")
replace_once(config, 'static const char *APPS_DEFAULT = "2,1,8,10,14,15,11,12,13,9,3,6";', 'static const char *APPS_DEFAULT = "2,1,8,10,14,15,11,12,13,3,6";')
replace_once(config, "  if (!cfg.qrOn && cfg.startTile == 1) cfg.startTile = 0;", "  cfg.qrOn = false;\n  if (cfg.startTile == 1) cfg.startTile = 0;")

mic = ROOT / "src" / "mic.h"
replace_once(mic, "// Microphone: an I2S digital MEMS mic (INMP441 / SPH0645 / MSM261 type) wired to IO21, IO22 and IO35.\n// IO35 is input-only, so it is the data line (SD); IO21 and IO22 are the bit clock (SCK) and the word select (WS).", "// ES3C28P I2S: codec microphone data on GPIO8, bit clock GPIO5, word select GPIO7.")
replace_once(mic, "static const int MIC_PIN_A = 21;\nstatic const int MIC_PIN_B = 22;\nstatic const int MIC_PIN_SD = 35;", "static const int MIC_PIN_A = 7;\nstatic const int MIC_PIN_B = 5;\nstatic const int MIC_PIN_SD = 8;")
print("Prepared source for ES3C28P: 320x240 landscape, FT6336G, SD_MMC, QR hidden.")
