from verifier import ScamVerifier

def run_p1_tests():
    print("=" * 65)
    print(" 🧪 TESTING PROCESS 1: SEBI REGISTRATION LOOKUP ")
    print("=" * 65)

    verifier = ScamVerifier()

    test_cases = [
        {
            "name": "Case 1: Legitimate Entity & Matching Handle",
            "text": "Join official zerodha channel! Reg: INZ000031633",
            "username": "zerodha",
            "expected": "GREEN"
        },
        {
            "name": "Case 2: Real SEBI ID with Fake/Misleading Username (IMPERSONATION)",
            "text": "Guaranteed Nifty Calls! Reg: INZ000031633",
            "username": "fake_nifty_guru_99",
            "expected": "YELLOW"
        },
        {
            "name": "Case 3: Fake or Unregistered SEBI ID",
            "text": "Official Registered Group: INZ999999999",
            "username": "scam_channel",
            "expected": "RED"
        }
    ]

    for case in test_cases:
        print(f"\n▶ Running [{case['name']}]...")
        res = verifier.verify(input_text=case["text"], claimed_username=case["username"])
        print(f"  Badge    : {res['badge']}")
        print(f"  Reason En: {res['reason_en']}")
        print(f"  Reason Hi: {res['reason_hi']}")

    print("\n" + "=" * 65)

if __name__ == "__main__":
    run_p1_tests()