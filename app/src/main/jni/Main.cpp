#include <pthread.h>
#include <jni.h>
#include <unistd.h>

#include "Includes/obfuscate.h"
#include "Includes/SakuraAdachiTool/Adachi.h"

#define targetLibName OBFUSCATE("libil2cpp.so")

#include "Includes/Logger.h"
#include "Includes/Macros.h"
#include "GamePatch.h"
#include "HookGame.h"

void *hook_thread(void *) {
    while (!isLibraryLoaded(targetLibName)) {
        usleep(200000);
    }

    sleep(2);
    AppendHsahcTrace("bootstrap", "thread", "libil2cpp detected; starting hook install");
    CallHookGame();
    return nullptr;
}

extern "C"
JNIEXPORT jobjectArray JNICALL
Java_com_android_support_CkHomuraMenu_GetFeatureList(JNIEnv *env, jobject) {
    jobjectArray ret;

    const char *features[] = {
        OBFUSCATE("Category_HSAHC Trace"),
        OBFUSCATE("1_Toggle_Enable version update trace_True"),
        OBFUSCATE("2_Button_Clear trace log"),
        OBFUSCATE("3_Button_Write test log"),
        OBFUSCATE("RichTextView_Log file: /data/data/com.lta.hsahc.aligames/files/hsahc_hook.log"),
        OBFUSCATE("RichTextView_Target library: libil2cpp.so"),
        OBFUSCATE("RichTextView_Current offsets are verified for arm64 build only"),
    };

    int total = (sizeof features / sizeof features[0]);
    ret = (jobjectArray) env->NewObjectArray(
        total,
        env->FindClass(OBFUSCATE("java/lang/String")),
        env->NewStringUTF("")
    );

    for (int i = 0; i < total; i++) {
        env->SetObjectArrayElement(ret, i, env->NewStringUTF(features[i]));
    }

    return ret;
}

extern "C"
JNIEXPORT void JNICALL
Java_com_android_support_Preferences_Changes(JNIEnv *env, jclass, jobject,
                                             jint featNum, jstring featName, jint value,
                                             jboolean boolean, jstring str) {
    const char *feature_name = featName != nullptr ? env->GetStringUTFChars(featName, 0) : "";
    const char *text_value = str != nullptr ? env->GetStringUTFChars(str, 0) : "";

    LOGD("Feature name: %d - %s | Value: = %d | Bool: = %d | Text: = %s",
         featNum, feature_name, value, boolean, text_value);

    switch (featNum) {
        case 1:
            gHsahcTraceEnabled = boolean;
            AppendHsahcTrace("system", "toggle", std::string("trace=") + (boolean ? "on" : "off"));
            break;
        case 2:
            ClearHsahcLog();
            break;
        case 3:
            WriteTestTraceLog();
            break;
        default:
            break;
    }

    if (featName != nullptr) {
        env->ReleaseStringUTFChars(featName, feature_name);
    }
    if (str != nullptr) {
        env->ReleaseStringUTFChars(str, text_value);
    }
}

__attribute__((constructor))
void lib_main() {
    pthread_t hook;
    pthread_create(&hook, nullptr, hook_thread, nullptr);
}

extern "C"
JNIEXPORT jobjectArray JNICALL
Java_com_android_support_CkHomuraMenu_SettingsList(JNIEnv *env, jobject) {
    jobjectArray ret;

    const char *features[] = {
        OBFUSCATE("Category_Settings"),
        OBFUSCATE("-1_Toggle_Save menu state"),
        OBFUSCATE("-6_Button_<font color='red'>Close settings</font>"),
    };

    int total = (sizeof features / sizeof features[0]);
    ret = (jobjectArray) env->NewObjectArray(
        total,
        env->FindClass(OBFUSCATE("java/lang/String")),
        env->NewStringUTF("")
    );

    for (int i = 0; i < total; i++) {
        env->SetObjectArrayElement(ret, i, env->NewStringUTF(features[i]));
    }

    return ret;
}

extern "C"
JNIEXPORT jstring JNICALL
Java_com_android_support_CkHomuraMenu_Icon(JNIEnv *env, jobject) {
    return env->NewStringUTF(
        OBFUSCATE(
            "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"));
}
