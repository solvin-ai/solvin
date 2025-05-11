# repro.py
import pandas as pd
from datetime import datetime
import sys
import traceback
import re # Import regex

# --- Configuration ---
# Loosen the check: Look for the pattern rather than exact dtype string
EXPECTED_ERROR_PATTERN = r"Invalid comparison between dtype=datetime64\[[a-z]+\] and date"

# --- Functions ---
def run_test():
    """Runs the test cases to reproduce the issue."""
    print(f"Python version: {sys.version}")
    print(f"Pandas version: {pd.__version__}")
    print("-" * 30)

    comparison_date = datetime.now().date()
    print(f"Comparison date: {comparison_date}")
    print("-" * 30)

    # --- Case 1: Mixed NaT and valid date (should work) ---
    print("Test Case 1: Series with mixed NaT and valid datetime")
    case1_success = False
    try:
        s_mixed = pd.Series([pd.NaT, "1/1/2020 10:00:00"])
        s_mixed = pd.to_datetime(s_mixed) # Let pandas infer precision
        print("Original Series (Mixed):\n", s_mixed)
        print("dtype:", s_mixed.dtype)

        dates_mixed = s_mixed.dt.date
        print("\nSeries after .dt.date (Mixed):\n", dates_mixed)
        print("dtype:", dates_mixed.dtype) # Should be object

        if dates_mixed.dtype != object:
             print(f"\nERROR: Case 1 failed: Expected object dtype from .dt.date, but got {dates_mixed.dtype}")
             return False # Cannot proceed if baseline is wrong

        result_mixed = dates_mixed.le(comparison_date)
        print("\nComparison Result (Mixed):\n", result_mixed)
        print("dtype:", result_mixed.dtype) # Should be bool
        print("Test Case 1: Comparison executed without error (as expected).")
        case1_success = True

    except Exception as e:
        print(f"\nERROR: Unexpected exception in Case 1: {e}")
        traceback.print_exc()
        # If the "working" case fails, we can't reliably test the bug
        return False

    print("-" * 30)

    # --- Case 2: All NaT values (should trigger the bug or reveal the dtype issue) ---
    print("Test Case 2: Series with only NaT values")
    try:
        s_all_nat = pd.Series([pd.NaT, pd.NaT])
        s_all_nat = pd.to_datetime(s_all_nat) # Let pandas infer precision
        print("Original Series (All NaT):\n", s_all_nat)
        print("dtype:", s_all_nat.dtype)

        dates_all_nat = s_all_nat.dt.date
        print("\nSeries after .dt.date (All NaT):\n", dates_all_nat)
        print("dtype:", dates_all_nat.dtype) # <<< This is where the bug manifests initially

        # Explicitly check the dtype returned by .dt.date
        if dates_all_nat.dtype != object:
            print(f"\nISSUE DETECTED: .dt.date returned dtype '{dates_all_nat.dtype}' instead of 'object' for all-NaT Series.")
            # Now, attempt the comparison which is expected to fail because of the wrong dtype
            try:
                print(f"\nAttempting comparison: dates_all_nat.le({comparison_date}) which is expected to fail now...")
                dates_all_nat.le(comparison_date)
                # If it somehow succeeds, it's unexpected
                print("\nERROR: Comparison succeeded unexpectedly after wrong dtype from .dt.date.")
                return False
            except TypeError as te:
                error_message = str(te)
                print(f"\nCaught expected TypeError due to wrong dtype: {error_message}")
                if re.search(EXPECTED_ERROR_PATTERN, error_message):
                     print("\nSUCCESS: reproduced issue. Root cause is .dt.date returning wrong dtype for all-NaT input, leading to comparison TypeError.")
                     return True # Reproduced the chain of events
                else:
                     print(f"\nERROR: Caught TypeError, but message format unexpected: {error_message}")
                     traceback.print_exc()
                     return False
            except Exception as e_inner:
                 print(f"\nERROR: Unexpected exception during comparison after wrong dtype: {e_inner}")
                 traceback.print_exc()
                 return False
        else:
            # If .dt.date *did* return object, proceed with the comparison
            print(f"\n.dt.date correctly returned 'object' dtype. Proceeding with comparison...")
            print(f"Attempting comparison: dates_all_nat.le({comparison_date})")
            result_all_nat = dates_all_nat.le(comparison_date)

            # If we reach here, the bug was NOT reproduced in the comparison step itself
            print("\nComparison Result (All NaT):\n", result_all_nat)
            print("dtype:", result_all_nat.dtype)

            expected_fixed_result = pd.Series([False, False], dtype=bool)
            if result_all_nat.equals(expected_fixed_result):
                 print("\nFAILURE: did not reproduce issue. .dt.date returned correct dtype and comparison succeeded as expected in fixed versions.")
            else:
                 print(f"\nFAILURE: did not reproduce issue. Comparison succeeded but returned unexpected result:\n{result_all_nat}")
            return False # Indicate failure to reproduce

    except Exception as e:
        # Catch any other unexpected error during Case 2 setup
        print(f"\nERROR: Unexpected exception during Case 2 setup: {e}")
        traceback.print_exc()
        return False # Indicate error

# --- Main Execution ---
if __name__ == "__main__":
    run_test()
