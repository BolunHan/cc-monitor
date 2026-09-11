# R8 / ProGuard rules for the release build.
#
# WHY THIS FILE EXISTS
# --------------------
# `flutter build apk --release` enables R8 (minify + shrink resources). R8 then
# removed MLKit's barcode classes, and the QR scanner failed at runtime with
# "An unexpected error occurred." (mobile_scanner's generic error, which is
# what it reports for MOBILE_SCANNER_BARCODE_ERROR).
#
# The cause is an upstream packaging bug in mobile_scanner 6.0.11: its Android
# module ships the correct keep rules in `android/proguard-rules.pro`, but the
# Android Gradle Plugin only propagates a *library's* `consumer-rules.pro` to
# the consuming app — and the plugin has no such file. So the rules never
# reached our build and R8 stripped the barcode implementation. Confirmed
# against R8's own report at build/app/outputs/mapping/release/usage.txt, which
# lists com.google.mlkit.vision.barcode.BarcodeScanner as removed.
#
# This is also why the bug only ever appeared after a *release* rebuild: debug
# APKs are not minified, so they always worked.
#
# Rules below mirror the plugin's own file, plus the MLKit internals the
# bundled `com.google.mlkit:barcode-scanning` variant loads by name.

# MLKit barcode scanning. Loaded reflectively, so R8 cannot see the references.
-keep class com.google.mlkit.** { *; }
-dontwarn com.google.mlkit.**
-keep class com.google.android.gms.internal.mlkit_vision_barcode.** { *; }
-dontwarn com.google.android.gms.internal.mlkit_vision_barcode.**

# MLKit model classes that resolve by name at runtime.
-keep class com.google.android.libraries.barhopper.** { *; }
-dontwarn com.google.android.libraries.barhopper.**

# The plugin itself talks to its native side over method channels.
-keep class dev.steenbakker.mobile_scanner.** { *; }

# Enums are looked up via valueOf(String) in several places.
-keepclassmembers class * extends java.lang.Enum {
    <fields>;
    public static **[] values();
    public static ** valueOf(java.lang.String);
}
