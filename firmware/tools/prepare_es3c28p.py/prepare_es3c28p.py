

# Expose all implemented apps except the removed Xiaozhi placeholder and VietQR.
replace_once(config, "static bool appInLauncher(int id) { return id != 0 && id != 4 && id != 5 && id != 7 && id != 9; }", "static bool appInLauncher(int id) { return id != 0 && id != 9; }")
replace_once(config, 'static const char *APPS_DEFAULT = "2,1,8,10,14,15,11,12,13,3,6";', 'static const char *APPS_DEFAULT = "2,1,8,10,14,15,11,12,13,4,5,7,3,6";')

# On the FNK0104B, the codec microphone data output is GPIO6 (GPIO8 is speaker data).
replace_once(mic, "static const int MIC_PIN_SD = 8;", "static const int MIC_PIN_SD = 6;")
print("Prepared FNK0104B hardware port: all implemented Zenix apps except VietQR.")
