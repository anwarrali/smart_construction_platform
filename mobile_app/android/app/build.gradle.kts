plugins {
    id("com.android.application")
    id("kotlin-android")
    id("dev.flutter.flutter-gradle-plugin")
}
dependencies {
  // Import the Firebase BoM
  implementation(platform("com.google.firebase:firebase-bom:34.18.0"))


  // TODO: Add the dependencies for Firebase products you want to use
  // When using the BoM, don't specify versions in Firebase dependencies
  // https://firebase.google.com/docs/android/setup#available-libraries
}
// Firebase's Gradle plugin, applied only when the project has actually been
// configured. `google-services.json` is git-ignored (it is per-Firebase-project
// configuration, not source), so applying this unconditionally would fail the
// build on a fresh clone with a message that says nothing about the real cause.
// With the file absent the app still builds and runs; push is simply
// unavailable, which is exactly how every other layer degrades.
val googleServicesConfig = file("google-services.json")
if (googleServicesConfig.exists()) {
    apply(plugin = "com.google.gms.google-services")
} else {
    logger.lifecycle(
        "android/app/google-services.json not found — building without Firebase " +
        "push. See docs/NOTIFICATIONS.md to configure it."
    )
}

val androidKeystorePath = System.getenv("ANDROID_KEYSTORE_PATH")
val androidKeystorePassword = System.getenv("ANDROID_KEYSTORE_PASSWORD")
val androidKeyAlias = System.getenv("ANDROID_KEY_ALIAS")
val androidKeyPassword = System.getenv("ANDROID_KEY_PASSWORD")
val ciReleaseSigningAvailable = listOf(
    androidKeystorePath,
    androidKeystorePassword,
    androidKeyAlias,
    androidKeyPassword,
).all { !it.isNullOrBlank() }

android {
    namespace = "com.example.mobile_app"
    compileSdk = flutter.compileSdkVersion
    // Native Flutter plugins in this app are built against NDK 27.
    // Android NDK releases are backward compatible, so use the highest
    // version required by the plugin set.
    ndkVersion = "27.0.12077973"

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }

    kotlinOptions {
        jvmTarget = JavaVersion.VERSION_11.toString()
    }

    defaultConfig {
        // TODO: Specify your own unique Application ID (https://developer.android.com/studio/build/application-id.html).
        applicationId = "com.example.mobile_app"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        // record_android 1.5+ uses APIs introduced in Android 6.0.
        minSdk = 23
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
        manifestPlaceholders["usesCleartextTraffic"] = "false"
    }

    val ciReleaseSigning = if (ciReleaseSigningAvailable) {
        signingConfigs.create("ciRelease") {
            storeFile = file(androidKeystorePath!!)
            storePassword = androidKeystorePassword
            keyAlias = androidKeyAlias
            keyPassword = androidKeyPassword
        }
    } else {
        null
    }

    buildTypes {
        debug {
            // Local physical-device testing may use the development computer's
            // LAN HTTP address. Release builds require HTTPS.
            manifestPlaceholders["usesCleartextTraffic"] = "true"
        }
        release {
            // Local and unsigned-CI workflows retain the existing debug-key
            // fallback. Store releases can opt in through environment variables
            // and a separately mounted keystore; no secret is stored here.
            signingConfig = ciReleaseSigning ?: signingConfigs.getByName("debug")
            manifestPlaceholders["usesCleartextTraffic"] = "false"
        }
    }
}

flutter {
    source = "../.."
}
