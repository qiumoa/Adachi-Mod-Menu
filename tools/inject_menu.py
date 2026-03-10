#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ANDROID_NS = "{http://schemas.android.com/apk/res/android}"
APKTOOL_URL = "https://github.com/iBotPeaches/Apktool/releases/download/v2.9.3/apktool_2.9.3.jar"
UBER_APK_SIGNER_URL = "https://github.com/patrickfav/uber-apk-signer/releases/download/v1.3.0/uber-apk-signer-1.3.0.jar"
MENU_CLASS = "Lcom/android/support/CkHomuraMain;"
MENU_INVOKE = "    invoke-static {p0}, Lcom/android/support/CkHomuraMain;->Start(Landroid/app/Activity;)V"


def run(command: list[str], cwd: Path | None = None) -> None:
    subprocess.run(command, cwd=str(cwd) if cwd else None, check=True)


def ensure_apktool(apktool_jar: Path) -> Path:
    if apktool_jar.is_file():
        return apktool_jar

    apktool_jar.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(APKTOOL_URL, apktool_jar)
    return apktool_jar


def ensure_uber_apk_signer(uber_signer_jar: Path) -> Path:
    if uber_signer_jar.is_file():
        return uber_signer_jar

    uber_signer_jar.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(UBER_APK_SIGNER_URL, uber_signer_jar)
    return uber_signer_jar


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare/finalize Adachi menu injection into a target APK.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="Decode target APK and inject launcher entry point.")
    prepare.add_argument("--target-apk", required=True, help="Path to the target APK.")
    prepare.add_argument("--workspace", required=True, help="Workspace directory to create.")
    prepare.add_argument("--apktool-jar", default="tools/apktool.jar", help="Path to apktool jar. Auto-downloaded if missing.")
    prepare.add_argument("--launcher-activity", default="", help="Optional fully-qualified launcher activity override.")
    prepare.add_argument("--force", action="store_true", help="Overwrite the workspace if it already exists.")

    finalize = subparsers.add_parser("finalize", help="Copy menu payload into a prepared workspace, then rebuild and sign.")
    finalize.add_argument("--workspace", required=True, help="Prepared workspace directory.")
    finalize.add_argument("--output-apk", required=True, help="Signed output APK path.")
    finalize.add_argument("--apktool-jar", default="tools/apktool.jar", help="Path to apktool jar. Auto-downloaded if missing.")
    finalize.add_argument("--menu-apk", default="", help="Optional compiled menu APK. If omitted, payload is read from workspace/payload.")

    return parser.parse_args()


def decode_apk(apktool_jar: Path, apk_path: Path, output_dir: Path) -> None:
    run(["java", "-jar", str(apktool_jar), "d", "-f", str(apk_path), "-o", str(output_dir)])


def build_apk(apktool_jar: Path, project_dir: Path, output_apk: Path) -> None:
    run(["java", "-jar", str(apktool_jar), "b", str(project_dir), "-o", str(output_apk)])


def strip_apktool_incompatible_manifest_attrs(manifest_path: Path) -> list[str]:
    if not manifest_path.is_file():
        return []

    text = manifest_path.read_text(encoding="utf-8")
    original = text
    removed: list[str] = []

    for attribute in (
        "android:compileSdkVersion",
        "android:compileSdkVersionCodename",
        "android:appComponentFactory",
    ):
        text, count = re.subn(rf"\s+{re.escape(attribute)}=\"[^\"]*\"", "", text)
        if count:
            removed.append(attribute)

    if text != original:
        manifest_path.write_text(text, encoding="utf-8", newline="\n")

    return removed


def resolve_component_name(package_name: str, component_name: str) -> str:
    if component_name.startswith("."):
        return f"{package_name}{component_name}"
    if "." not in component_name:
        return f"{package_name}.{component_name}"
    return component_name


def is_launcher_component(element: ET.Element) -> bool:
    for intent_filter in element.findall("intent-filter"):
        has_main = False
        has_launcher = False
        for action in intent_filter.findall("action"):
            if action.get(f"{ANDROID_NS}name") == "android.intent.action.MAIN":
                has_main = True
        for category in intent_filter.findall("category"):
            if action := category.get(f"{ANDROID_NS}name"):
                if action == "android.intent.category.LAUNCHER":
                    has_launcher = True
        if has_main and has_launcher:
            return True
    return False


def find_launcher_activity(manifest_path: Path, override: str) -> str:
    if override:
        return override

    tree = ET.parse(manifest_path)
    root = tree.getroot()
    package_name = root.get("package")
    application = root.find("application")
    if application is None or package_name is None:
        raise RuntimeError("failed to parse AndroidManifest.xml")

    for tag_name in ("activity", "activity-alias"):
        for element in application.findall(tag_name):
            if not is_launcher_component(element):
                continue
            if tag_name == "activity-alias":
                target_activity = element.get(f"{ANDROID_NS}targetActivity")
                if target_activity:
                    return resolve_component_name(package_name, target_activity)
            activity_name = element.get(f"{ANDROID_NS}name")
            if activity_name:
                return resolve_component_name(package_name, activity_name)

    raise RuntimeError("launcher activity not found in AndroidManifest.xml")


def find_smali_file(decoded_dir: Path, class_name: str) -> Path:
    relative_path = Path(*class_name.split(".")).with_suffix(".smali")
    for smali_dir in sorted(decoded_dir.glob("smali*")):
        candidate = smali_dir / relative_path
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"launcher smali file not found for {class_name}")


def next_smali_dir(decoded_dir: Path) -> Path:
    max_index = 1
    for path in decoded_dir.glob("smali*"):
        name = path.name
        if name == "smali":
            max_index = max(max_index, 1)
            continue
        match = re.fullmatch(r"smali_classes(\d+)", name)
        if match:
            max_index = max(max_index, int(match.group(1)))
    return decoded_dir / f"smali_classes{max_index + 1}"


def patch_on_window_focus(smali_path: Path) -> None:
    lines = smali_path.read_text(encoding="utf-8").splitlines()
    if any(MENU_INVOKE.strip() in line for line in lines):
        return

    super_class = "Landroid/app/Activity;"
    for line in lines:
        if line.startswith(".super "):
            super_class = line.split(" ", 1)[1].strip()
            break

    method_start = None
    method_end = None
    for index, line in enumerate(lines):
        if re.match(r"^\.method\b.* onWindowFocusChanged\(Z\)V$", line.strip()):
            method_start = index
            continue
        if method_start is not None and line.strip() == ".end method":
            method_end = index
            break

    if method_start is not None and method_end is not None:
        insert_index = method_start + 1
        while insert_index < method_end:
            stripped = lines[insert_index].strip()
            if stripped == "" or stripped.startswith(".") or stripped.startswith("#"):
                insert_index += 1
                continue
            break
        lines.insert(insert_index, "")
        lines.insert(insert_index, MENU_INVOKE)
    else:
        method_block = [
            "",
            ".method public onWindowFocusChanged(Z)V",
            "    .locals 0",
            "",
            MENU_INVOKE,
            "",
            f"    invoke-super {{p0, p1}}, {super_class}->onWindowFocusChanged(Z)V",
            "",
            "    return-void",
            ".end method",
        ]
        lines.extend(method_block)

    smali_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def write_workspace_readme(workspace: Path, launcher_activity: str) -> None:
    readme = workspace / "README.txt"
    readme.write_text(
        "\n".join([
            "Adachi menu injection workspace",
            "",
            "1. decoded/ 已经是打好注入点的目标 APK 反编译目录。",
            "2. payload/ 是你后续放菜单产物的位置。",
            "",
            "支持两种放法：",
            "A. 直接放一个编译好的菜单 APK：payload/menu.apk",
            "B. 手动放入菜单产物：",
            "   - payload/smali/com/android/support/... 或 payload/smali_classes*/com/android/support/...",
            "   - payload/lib/<abi>/libSakuraAdachi.so",
            "",
            "如果你只有 raw dex，本脚本暂不直接吃 dex；请先转成 smali，或者直接放 menu.apk。",
            "",
            f"当前已注入的启动类：{launcher_activity}",
            "",
            "完成后运行：",
            "python tools/inject_menu.py finalize --workspace <workspace> --output-apk <output.apk>",
            "",
        ]) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def save_meta(workspace: Path, data: dict[str, str]) -> None:
    (workspace / "meta.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def load_meta(workspace: Path) -> dict[str, str]:
    meta_path = workspace / "meta.json"
    if not meta_path.is_file():
        raise FileNotFoundError(f"meta.json not found in workspace: {workspace}")
    return json.loads(meta_path.read_text(encoding="utf-8"))


def build_tools_dir() -> Path:
    sdk_root = os.environ.get("ANDROID_SDK_ROOT") or os.environ.get("ANDROID_HOME")
    if not sdk_root:
        raise RuntimeError("ANDROID_SDK_ROOT or ANDROID_HOME is required for zipalign/apksigner")

    build_tools_root = Path(sdk_root) / "build-tools"
    candidates = [path for path in build_tools_root.iterdir() if path.is_dir()]
    if not candidates:
        raise RuntimeError("Android build-tools directory is missing")

    def version_key(path: Path) -> tuple[int, ...]:
        return tuple(int(part) for part in path.name.split(".") if part.isdigit())

    return sorted(candidates, key=version_key)[-1]


def sign_apk(unsigned_apk: Path, output_apk: Path) -> None:
    try:
        tools_dir = build_tools_dir()
    except RuntimeError:
        tools_dir = None

    if tools_dir is not None:
        zipalign = tools_dir / ("zipalign.exe" if os.name == "nt" else "zipalign")
        apksigner = tools_dir / ("apksigner.bat" if os.name == "nt" else "apksigner")

        if not zipalign.exists() or not apksigner.exists():
            raise RuntimeError("zipalign/apksigner not found in Android build-tools")

        aligned_apk = unsigned_apk.with_name(f"{unsigned_apk.stem}-aligned.apk")
        keystore = unsigned_apk.with_name("debug.keystore")

        run([
            "keytool",
            "-genkeypair",
            "-keystore",
            str(keystore),
            "-storepass",
            "android",
            "-keypass",
            "android",
            "-alias",
            "androiddebugkey",
            "-dname",
            "CN=Android Debug,O=Android,C=US",
            "-keyalg",
            "RSA",
            "-keysize",
            "2048",
            "-validity",
            "10000",
        ])

        run([str(zipalign), "-f", "4", str(unsigned_apk), str(aligned_apk)])
        run([
            str(apksigner),
            "sign",
            "--ks",
            str(keystore),
            "--ks-pass",
            "pass:android",
            "--key-pass",
            "pass:android",
            "--out",
            str(output_apk),
            str(aligned_apk),
        ])
        run([str(apksigner), "verify", str(output_apk)])
        return

    uber_signer_jar = ensure_uber_apk_signer(Path(__file__).resolve().parent / "uber-apk-signer.jar")
    print("I: ANDROID_SDK_ROOT/ANDROID_HOME not set; using uber-apk-signer for zipalign/signing")

    with tempfile.TemporaryDirectory(prefix="adachi-ubersigner-") as temp_dir:
        out_dir = Path(temp_dir) / "out"
        out_dir.mkdir(parents=True, exist_ok=True)

        run([
            "java",
            "-jar",
            str(uber_signer_jar),
            "--apks",
            str(unsigned_apk),
            "--out",
            str(out_dir),
        ])

        candidates = sorted(out_dir.glob("*.apk"), key=lambda path: path.stat().st_mtime, reverse=True)
        if not candidates:
            raise RuntimeError("uber-apk-signer did not produce any APK output")

        shutil.copy2(candidates[0], output_apk)


def remove_existing_menu(decoded_dir: Path) -> None:
    for smali_dir in decoded_dir.glob("smali*"):
        support_dir = smali_dir / "com" / "android" / "support"
        if support_dir.exists():
            shutil.rmtree(support_dir)

    lib_root = decoded_dir / "lib"
    if lib_root.is_dir():
        for lib_path in lib_root.glob("*/libSakuraAdachi.so"):
            lib_path.unlink()


def copy_menu_smali_from_decoded(source_decoded_dir: Path, target_decoded_dir: Path) -> bool:
    copied = False
    for smali_dir in sorted(source_decoded_dir.glob("smali*")):
        source_pkg = smali_dir / "com" / "android" / "support"
        if not source_pkg.is_dir():
            continue
        destination_root = next_smali_dir(target_decoded_dir)
        destination_pkg = destination_root / "com" / "android" / "support"
        destination_pkg.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source_pkg, destination_pkg, dirs_exist_ok=True)
        copied = True
    return copied


def copy_menu_libs_from_apk(menu_apk: Path, target_decoded_dir: Path) -> bool:
    import zipfile

    copied = False
    with zipfile.ZipFile(menu_apk, "r") as archive:
        for name in archive.namelist():
            if not name.startswith("lib/") or not name.endswith("/libSakuraAdachi.so"):
                continue
            destination = target_decoded_dir / Path(name)
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(name, "r") as src, open(destination, "wb") as dst:
                shutil.copyfileobj(src, dst)
            copied = True
    return copied


def copy_payload_smali(payload_dir: Path, target_decoded_dir: Path) -> bool:
    copied = False
    for candidate in sorted(payload_dir.iterdir()):
        if not candidate.is_dir() or not candidate.name.startswith("smali"):
            continue
        source_pkg = candidate / "com" / "android" / "support"
        if not source_pkg.is_dir():
            continue
        destination_root = next_smali_dir(target_decoded_dir)
        destination_pkg = destination_root / "com" / "android" / "support"
        destination_pkg.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source_pkg, destination_pkg, dirs_exist_ok=True)
        copied = True
    return copied


def copy_payload_libs(payload_dir: Path, target_decoded_dir: Path) -> bool:
    lib_root = payload_dir / "lib"
    if not lib_root.is_dir():
        return False

    copied = False
    for abi_dir in sorted(lib_root.iterdir()):
        if not abi_dir.is_dir():
            continue
        so_path = abi_dir / "libSakuraAdachi.so"
        if not so_path.is_file():
            continue
        destination = target_decoded_dir / "lib" / abi_dir.name / "libSakuraAdachi.so"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(so_path, destination)
        copied = True
    return copied


def apply_menu_payload(workspace: Path, menu_apk_override: str, apktool_jar: Path) -> None:
    payload_dir = workspace / "payload"
    decoded_dir = workspace / "decoded"

    remove_existing_menu(decoded_dir)

    if (payload_dir / "dex").is_dir():
        raise RuntimeError("payload/dex is not supported directly. Please provide smali directories or a compiled menu.apk.")

    menu_apk = Path(menu_apk_override).resolve() if menu_apk_override else payload_dir / "menu.apk"
    if menu_apk.is_file():
        with tempfile.TemporaryDirectory(prefix="adachi-menu-decode-") as temp_dir:
            temp_root = Path(temp_dir)
            menu_decoded = temp_root / "menu"
            decode_apk(apktool_jar, menu_apk, menu_decoded)
            smali_ok = copy_menu_smali_from_decoded(menu_decoded, decoded_dir)
            libs_ok = copy_menu_libs_from_apk(menu_apk, decoded_dir)
            if not smali_ok:
                raise RuntimeError("menu.apk does not contain com/android/support smali")
            if not libs_ok:
                raise RuntimeError("menu.apk does not contain libSakuraAdachi.so")
        return

    smali_ok = copy_payload_smali(payload_dir, decoded_dir)
    libs_ok = copy_payload_libs(payload_dir, decoded_dir)

    if not smali_ok:
        raise RuntimeError("menu payload smali not found. Expected payload/smali/com/android/support or payload/smali_classes*/com/android/support.")
    if not libs_ok:
        raise RuntimeError("menu payload libs not found. Expected payload/lib/<abi>/libSakuraAdachi.so.")


def prepare_command(args: argparse.Namespace) -> int:
    target_apk = Path(args.target_apk).resolve()
    workspace = Path(args.workspace).resolve()
    apktool_jar = ensure_apktool(Path(args.apktool_jar).resolve())

    if not target_apk.is_file():
        raise FileNotFoundError(f"target APK not found: {target_apk}")

    if workspace.exists():
        if not args.force:
            raise FileExistsError(f"workspace already exists: {workspace}. Re-run with --force to overwrite.")
        shutil.rmtree(workspace)

    decoded_dir = workspace / "decoded"
    payload_dir = workspace / "payload"
    payload_dir.mkdir(parents=True, exist_ok=True)

    decode_apk(apktool_jar, target_apk, decoded_dir)

    launcher_activity = find_launcher_activity(decoded_dir / "AndroidManifest.xml", args.launcher_activity)
    launcher_smali = find_smali_file(decoded_dir, launcher_activity)
    patch_on_window_focus(launcher_smali)

    save_meta(workspace, {
        "target_apk": str(target_apk),
        "decoded_dir": str(decoded_dir),
        "launcher_activity": launcher_activity,
        "launcher_smali": str(launcher_smali.relative_to(decoded_dir).as_posix()),
    })
    write_workspace_readme(workspace, launcher_activity)

    print(f"prepared workspace: {workspace}")
    print(f"launcher activity: {launcher_activity}")
    print(f"patched smali: {launcher_smali}")
    return 0


def finalize_command(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    output_apk = Path(args.output_apk).resolve()
    apktool_jar = ensure_apktool(Path(args.apktool_jar).resolve())

    if not workspace.is_dir():
        raise FileNotFoundError(f"workspace not found: {workspace}")

    meta = load_meta(workspace)
    decoded_dir = Path(meta.get("decoded_dir", ""))
    if not decoded_dir.is_dir():
        fallback_decoded = workspace / "decoded"
        if fallback_decoded.is_dir():
            decoded_dir = fallback_decoded
        else:
            raise FileNotFoundError(f"decoded directory not found: {decoded_dir}")

    removed_attrs = strip_apktool_incompatible_manifest_attrs(decoded_dir / "AndroidManifest.xml")
    if removed_attrs:
        print(f"I: Stripped manifest attributes for apktool compatibility: {', '.join(removed_attrs)}")

    apply_menu_payload(workspace, args.menu_apk, apktool_jar)

    output_apk.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="adachi-finalize-") as temp_dir:
        unsigned_apk = Path(temp_dir) / "unsigned.apk"
        build_apk(apktool_jar, decoded_dir, unsigned_apk)
        sign_apk(unsigned_apk, output_apk)

    print(f"finalized launcher activity: {meta['launcher_activity']}")
    print(f"created signed APK: {output_apk}")
    return 0


def main() -> int:
    args = parse_args()
    if args.command == "prepare":
        return prepare_command(args)
    if args.command == "finalize":
        return finalize_command(args)
    raise RuntimeError(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
