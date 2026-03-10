#pragma once

#ifndef HSAHC_HOOKGAME_H
#define HSAHC_HOOKGAME_H

#include <fstream>
#include <mutex>
#include <sstream>
#include <string>

#include "Includes/Logger.h"
#include "Includes/Struct.h"
#include "Includes/Utils.h"
#include "Includes/Macros.h"

static const char *kHsahcLogPath = "/data/data/com.lta.hsahc.aligames/files/hsahc_hook.log";
static bool gHsahcTraceEnabled = true;
static bool gHsahcHooksInstalled = false;
static std::mutex gHsahcLogMutex;
static uint64_t gHsahcSequence = 0;

inline std::string Utf16ToUtf8(const Il2CppChar *chars, int length) {
    std::string output;
    if (chars == nullptr || length <= 0) {
        return output;
    }

    output.reserve(static_cast<size_t>(length));
    for (int i = 0; i < length; ++i) {
        uint32_t codepoint = chars[i];

        if (codepoint >= 0xD800 && codepoint <= 0xDBFF && i + 1 < length) {
            uint32_t low = chars[i + 1];
            if (low >= 0xDC00 && low <= 0xDFFF) {
                codepoint = 0x10000 + (((codepoint - 0xD800) << 10) | (low - 0xDC00));
                ++i;
            }
        }

        if (codepoint <= 0x7F) {
            output.push_back(static_cast<char>(codepoint));
        } else if (codepoint <= 0x7FF) {
            output.push_back(static_cast<char>(0xC0 | (codepoint >> 6)));
            output.push_back(static_cast<char>(0x80 | (codepoint & 0x3F)));
        } else if (codepoint <= 0xFFFF) {
            output.push_back(static_cast<char>(0xE0 | (codepoint >> 12)));
            output.push_back(static_cast<char>(0x80 | ((codepoint >> 6) & 0x3F)));
            output.push_back(static_cast<char>(0x80 | (codepoint & 0x3F)));
        } else {
            output.push_back(static_cast<char>(0xF0 | (codepoint >> 18)));
            output.push_back(static_cast<char>(0x80 | ((codepoint >> 12) & 0x3F)));
            output.push_back(static_cast<char>(0x80 | ((codepoint >> 6) & 0x3F)));
            output.push_back(static_cast<char>(0x80 | (codepoint & 0x3F)));
        }
    }

    return output;
}

inline std::string SafeString(Il2CppString *value) {
    if (value == nullptr) {
        return "<null>";
    }
    return Utf16ToUtf8(value->chars, value->length);
}

inline void AppendHsahcTrace(const char *stage, const char *type, const std::string &message) {
    std::lock_guard<std::mutex> lock(gHsahcLogMutex);

    std::ostringstream line;
    line << "[hsahc][" << stage << "][" << type << "][seq=" << gHsahcSequence++ << "] " << message;

    LOGI("%s", line.str().c_str());

    std::ofstream stream(kHsahcLogPath, std::ios::out | std::ios::app);
    if (stream.is_open()) {
        stream << line.str() << std::endl;
    }
}

inline void ClearHsahcLog() {
    std::lock_guard<std::mutex> lock(gHsahcLogMutex);
    std::ofstream stream(kHsahcLogPath, std::ios::out | std::ios::trunc);
    if (stream.is_open()) {
        stream << "[hsahc][system][reset] log cleared" << std::endl;
    }
    LOGI("%s", "[hsahc][system][reset] log cleared");
}

inline void WriteTestTraceLog() {
    AppendHsahcTrace("system", "test", "manual test log from menu");
}

#if defined(__aarch64__)

static Il2CppString *(*old_GetAppVersionNumber)(void *instance, void *a1, void *a2, void *a3) = nullptr;
static void (*old_SceneMgr_Start)(void *instance, void *a1, void *a2, void *a3) = nullptr;
static Il2CppString *(*old_LoadVersionCache)(void *instance, void *a1, void *a2, void *a3) = nullptr;
static void (*old_RequestGameControl)(void *instance, void *a1, void *a2, void *a3, void *a4) = nullptr;
static void (*old_RequestGameControlCallback)(void *instance, int isSucceed, void *a2, void *a3, void *a4) = nullptr;
static int (*old_VersionCompare)(void *instance, Il2CppString *current, Il2CppString *compare, void *a3, void *a4) = nullptr;
static void (*old_ParseServerInfo)(void *instance, void *a1, void *a2, void *a3, void *a4) = nullptr;
static void (*old_ShowUI)(void *instance, void *a1, void *a2, void *a3) = nullptr;
static void (*old_OnUpdateButtonClick)(void *instance, void *a1, void *a2, void *a3) = nullptr;
static void (*old_ConfirmCallback)(void *instance, int choice, void *a2, void *a3, void *a4) = nullptr;
static void (*old_VersionForceUpdateJump)(void *instance, void *a1, void *a2, void *a3) = nullptr;
static void (*old_OpenNativeBrowser)(void *instance, Il2CppString *url, void *a2, void *a3) = nullptr;

static Il2CppString *GetAppVersionNumber_Hook(void *instance, void *a1, void *a2, void *a3) {
    Il2CppString *result = old_GetAppVersionNumber(instance, a1, a2, a3);
    if (gHsahcTraceEnabled) {
        AppendHsahcTrace("display", "return", "GetAppVersionNumber=" + SafeString(result));
    }
    return result;
}

static void SceneMgr_Start_Hook(void *instance, void *a1, void *a2, void *a3) {
    if (gHsahcTraceEnabled) {
        AppendHsahcTrace("display", "enter", "SceneMgr.Start");
    }
    old_SceneMgr_Start(instance, a1, a2, a3);
}

static Il2CppString *LoadVersionCache_Hook(void *instance, void *a1, void *a2, void *a3) {
    Il2CppString *result = old_LoadVersionCache(instance, a1, a2, a3);
    if (gHsahcTraceEnabled) {
        AppendHsahcTrace("cache", "return", "LoadVersionCache=" + SafeString(result));
    }
    return result;
}

static void RequestGameControl_Hook(void *instance, void *a1, void *a2, void *a3, void *a4) {
    if (gHsahcTraceEnabled) {
        AppendHsahcTrace("decision", "enter", "RequestGameControl");
    }
    old_RequestGameControl(instance, a1, a2, a3, a4);
}

static void RequestGameControlCallback_Hook(void *instance, int isSucceed, void *a2, void *a3, void *a4) {
    if (gHsahcTraceEnabled) {
        AppendHsahcTrace("decision", "args", "RequestGameControlCallback isSucceed=" + std::to_string(isSucceed));
    }
    old_RequestGameControlCallback(instance, isSucceed, a2, a3, a4);
}

static int VersionCompare_Hook(void *instance, Il2CppString *current, Il2CppString *compare, void *a3, void *a4) {
    if (gHsahcTraceEnabled) {
        AppendHsahcTrace(
            "decision",
            "args",
            "VersionCompare current=" + SafeString(current) + " compare=" + SafeString(compare)
        );
    }

    int result = old_VersionCompare(instance, current, compare, a3, a4);

    if (gHsahcTraceEnabled) {
        AppendHsahcTrace("decision", "return", "VersionCompare result=" + std::to_string(result));
    }

    return result;
}

static void ParseServerInfo_Hook(void *instance, void *a1, void *a2, void *a3, void *a4) {
    if (gHsahcTraceEnabled) {
        AppendHsahcTrace("decision", "enter", "ParseServerInfo");
    }
    old_ParseServerInfo(instance, a1, a2, a3, a4);
}

static void ShowUI_Hook(void *instance, void *a1, void *a2, void *a3) {
    if (gHsahcTraceEnabled) {
        AppendHsahcTrace("ui", "enter", "ShowUI");
    }
    old_ShowUI(instance, a1, a2, a3);
}

static void OnUpdateButtonClick_Hook(void *instance, void *a1, void *a2, void *a3) {
    if (gHsahcTraceEnabled) {
        AppendHsahcTrace("ui", "enter", "OnUpdateButtonClick");
    }
    old_OnUpdateButtonClick(instance, a1, a2, a3);
}

static void ConfirmCallback_Hook(void *instance, int choice, void *a2, void *a3, void *a4) {
    if (gHsahcTraceEnabled) {
        AppendHsahcTrace("jump", "args", "ConfirmCallback choice=" + std::to_string(choice));
    }
    old_ConfirmCallback(instance, choice, a2, a3, a4);
}

static void VersionForceUpdateJump_Hook(void *instance, void *a1, void *a2, void *a3) {
    if (gHsahcTraceEnabled) {
        AppendHsahcTrace("jump", "enter", "VersionForceUpdateJump");
    }
    old_VersionForceUpdateJump(instance, a1, a2, a3);
}

static void OpenNativeBrowser_Hook(void *instance, Il2CppString *url, void *a2, void *a3) {
    if (gHsahcTraceEnabled) {
        AppendHsahcTrace("jump", "args", "OpenNativeBrowser url=" + SafeString(url));
    }
    old_OpenNativeBrowser(instance, url, a2, a3);
}

inline void InstallHsahcHooksArm64() {
    if (gHsahcHooksInstalled) {
        return;
    }

    AppendHsahcTrace("bootstrap", "install", "installing arm64 hooks");

    HOOK_LIB("libil2cpp.so", "0x01598EDC", GetAppVersionNumber_Hook, old_GetAppVersionNumber);
    HOOK_LIB("libil2cpp.so", "0x014A73C8", SceneMgr_Start_Hook, old_SceneMgr_Start);
    HOOK_LIB("libil2cpp.so", "0x012B2F14", LoadVersionCache_Hook, old_LoadVersionCache);
    HOOK_LIB("libil2cpp.so", "0x017331B8", RequestGameControl_Hook, old_RequestGameControl);
    HOOK_LIB("libil2cpp.so", "0x01733CBC", RequestGameControlCallback_Hook, old_RequestGameControlCallback);
    HOOK_LIB("libil2cpp.so", "0x017351B4", VersionCompare_Hook, old_VersionCompare);
    HOOK_LIB("libil2cpp.so", "0x017355C4", ParseServerInfo_Hook, old_ParseServerInfo);
    HOOK_LIB("libil2cpp.so", "0x016DE060", ShowUI_Hook, old_ShowUI);
    HOOK_LIB("libil2cpp.so", "0x016DE0A4", OnUpdateButtonClick_Hook, old_OnUpdateButtonClick);
    HOOK_LIB("libil2cpp.so", "0x01736F80", ConfirmCallback_Hook, old_ConfirmCallback);
    HOOK_LIB("libil2cpp.so", "0x0159AB40", VersionForceUpdateJump_Hook, old_VersionForceUpdateJump);
    HOOK_LIB("libil2cpp.so", "0x0159ABE0", OpenNativeBrowser_Hook, old_OpenNativeBrowser);

    gHsahcHooksInstalled = true;
    AppendHsahcTrace("bootstrap", "done", "arm64 hooks installed");
}

#endif

inline void CallHookGame() {
#if defined(__aarch64__)
    InstallHsahcHooksArm64();
#else
    AppendHsahcTrace("bootstrap", "skip", "current template only has verified HSAHC offsets for arm64");
#endif
}

#endif
