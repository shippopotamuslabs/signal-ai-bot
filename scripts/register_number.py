#!/usr/bin/env python3
"""
Interactive helper to register and verify your Signal phone number
using the native signal-cli binary or HTTP API.
"""

import asyncio
import os
import subprocess
import sys

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BIN_PATH = os.path.join(BASE_DIR, "bin", "signal-cli")
ENV_PATH = os.path.join(BASE_DIR, ".env")


def run_cmd(args):
    """Run a CLI command and return (stdout, stderr, exit_code)."""
    p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out, err = p.communicate()
    return out.strip(), err.strip(), p.returncode


def update_env_file(key, value):
    """Update or append a key=value pair in .env."""
    lines = []
    found = False
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r") as f:
            lines = f.readlines()

    new_lines = []
    for line in lines:
        if line.startswith(f"{key}="):
            new_lines.append(f"{key}={value}\n")
            found = True
        else:
            new_lines.append(line)

    if not found:
        new_lines.append(f"{key}={value}\n")

    with open(ENV_PATH, "w") as f:
        f.writelines(new_lines)


def main():
    print("=" * 65)
    print("      🚀 Signal Phone Number Registration Wizard")
    print("=" * 65)

    if not os.path.exists(BIN_PATH):
        print(f"[!] Warning: Native binary not found at {BIN_PATH}")
        print("    Falling back to standard instructions.")
        return

    # 1. Ask for Phone Number
    phone = input("\n[1/3] Enter your Tello phone number with country code (e.g. +14155552671): ").strip()
    if not phone.startswith("+"):
        print("[!] Error: Phone number must start with '+' (e.g. +14155552671)")
        return

    # 2. Ask for OpenRouter API Key if not already in .env
    current_key = ""
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r") as f:
            for l in f:
                if l.startswith("OPENROUTER_API_KEY="):
                    current_key = l.split("=", 1)[1].strip()

    if not current_key or current_key == "your_openrouter_api_key_here":
        api_key = input("\n[2/3] Enter your OpenRouter API Key (e.g. sk-or-v1-...): ").strip()
        if api_key:
            update_env_file("OPENROUTER_API_KEY", api_key)
            print("[+] Saved OPENROUTER_API_KEY to .env")
    else:
        print(f"\n[2/3] OpenRouter API Key already found in .env (starts with {current_key[:12]}...)")

    # 3. Request SMS Verification
    print(f"\n[3/3] Sending registration request for {phone} to Signal servers...")
    out, err, code = run_cmd([BIN_PATH, "-u", phone, "register"])

    # Check if CAPTCHA is required by Signal
    if code != 0 and ("captcha" in err.lower() or "captcha" in out.lower()):
        print("\n[!] Signal requires a quick CAPTCHA verification.")
        print("    1. Open this link in your browser:")
        print("       👉 https://signalcaptchas.org/registration/generate.html")
        print("    2. Complete the puzzle/checkbox.")
        print("    3. When it asks to open Signal or gives a signalcaptcha:// token, copy that full token.")
        
        captcha_token = input("\n[?] Paste the signalcaptcha://... token here: ").strip()
        if captcha_token.startswith("signalcaptcha://"):
            captcha_token = captcha_token.replace("signalcaptcha://", "")

        print(f"[*] Retrying registration with CAPTCHA for {phone}...")
        out, err, code = run_cmd([BIN_PATH, "-u", phone, "register", "--captcha", captcha_token])

    if code != 0:
        print(f"\n[!] Registration request failed:\n{err or out}")
        print("Tip: If SMS failed, you can also try voice call verification: `./bin/signal-cli -u " + phone + " register --voice`")
        return

    print("\n[+] Success! Signal has sent a 6-digit verification code via SMS to your phone.")
    
    # 4. Submit Verification Code
    sms_code = input("\n[?] Enter the 6-digit code received on your phone (e.g. 123-456): ").strip().replace("-", "")
    if not sms_code:
        print("[!] No code entered. Aborting.")
        return

    print(f"[*] Verifying code '{sms_code}' with Signal...")
    out, err, code = run_cmd([BIN_PATH, "-u", phone, "verify", sms_code])

    if code != 0:
        print(f"\n[!] Verification failed:\n{err or out}")
        return

    # Update .env
    update_env_file("SIGNAL_PHONE_NUMBER", phone)

    print("\n" + "=" * 65)
    print("🎉 SUCCESS! Your Signal bot number is now officially registered!")
    print("=" * 65)
    print("\nYour configuration is saved in `.env`.")
    print("\nTo start your bot right now, simply run:")
    print("   👉 python3 run_bot.py")
    print("\nThen add your bot's phone number to your family Signal group chat!")


if __name__ == "__main__":
    main()
