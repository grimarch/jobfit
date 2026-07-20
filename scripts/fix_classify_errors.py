"""Fix known classification errors in the DB.

Three classes of errors:
1. company_type='enterprise' — LLM confused type and stage; correct value is 'product'
2. Public sector institutions misclassified as 'product' — fix to 'public_sector'
3. Consulting/staffing firms misclassified as 'product', and vice versa — verified via web research

Usage:
    uv run python scripts/fix_classify_errors.py           # dry-run, show changes
    uv run python scripts/fix_classify_errors.py --apply   # apply to DB
    uv run python scripts/fix_classify_errors.py --firma Huzzle --apply
"""

import argparse
import sys
from collections import defaultdict

sys.path.insert(0, ".")


# Companies with verified correct company_type (web-researched).
# Key: exact firma string. Value: correct company_type (stage not touched).
_TYPE_FIXES: dict[str, str] = {
    # Public sector — government-owned or mandated institutions
    "DENIC eG": "public_sector",  # DE domain registry, nonprofit cooperative
    "BWI GmbH": "public_sector",
    "gematik GmbH": "public_sector",
    "Bundeskriminalamt": "public_sector",
    "Bundesverwaltungsamt": "public_sector",
    "Zentraler IT-Betrieb Justiz Niedersachsen": "public_sector",
    "Rundfunk Berlin-Brandenburg AdöR": "public_sector",
    "Hamburger Energienetze GmbH": "public_sector",
    "ALDB GmbH": "public_sector",
    "Dataport Recruiting": "public_sector",
    # Consulting/staffing — verified as service firms with no own product
    "men-in-motion GmbH": "consulting",
    "amaxo GmbH": "consulting",
    "SINC GmbH": "consulting",
    "sepp.med gmbh": "consulting",
    "Alexander Thamm GmbH": "consulting",
    "OEDIV": "consulting",
    "plusYou GmbH": "consulting",
    "VOQUZ Public GmbH": "consulting",
    "Tergos GmbH": "consulting",
    "Peagle GmbH": "consulting",
    "Iits": "consulting",
    "think about IT GmbH": "consulting",
    "Drees & Sommer SE": "consulting",
    "DG Service Hub GmbH Geschäftsstelle Rostock": "consulting",
    "citema systems GmbH": "consulting",
    "CANCOM SE": "consulting",
    "ATOS International": "consulting",
    "S-Markt & Mehrwert GmbH & Co. KG": "public_sector",
    "Alexianer IT GmbH": "public_sector",
    "Axians Infoma GmbH": "product",
    # Product — verified as companies building their own product/service
    "DekaBank Deutsche Girozentrale": "product",
    "TenneT TSO GmbH Unternehmensleitung": "product",
    "SIGNAL IDUNA Krankenversicherung a. G.": "product",
    "Workwise GmbH": "product",
    "qbees GmbH": "product",
    "Wölfel Group": "product",
    "SUMMIT IT CONSULT GmbH": "product",
    "NorCom": "product",
    "KUMAVISION AG": "product",
    "Huzzle": "consulting",
    "Hubside": "product",
    "Workwise GmbH": "product",
    "Deutsche Telekom MMS GmbH": "product",
    # Consulting — IT services/staffing, no own product
    "Franklin Fitch Limited": "consulting",  # IT recruitment/staffing firm (UK)
    "LZ Informatik": "consulting",  # Swiss IT managed services
    "TRIOLOGY GmbH": "consulting",  # web agency
    "TKD Solutions GmbH": "consulting",  # IT solutions/services
    "Inlogy GmbH": "consulting",  # custom software dev & consulting, no own product
}


def main(apply: bool, firma: str | None = None) -> None:
    from jobfit.db import get_session
    from jobfit.db.models import Classification as C

    tag = "APPLY" if apply else "DRY-RUN"
    scope = f"firma={firma!r}" if firma else "all"
    fixes: list[
        tuple[C, str, str, str, str]
    ] = []  # (row, old_type, old_stage, new_type, new_stage)

    with get_session() as session:
        q = session.query(C)
        if firma is not None:
            q = q.filter(C.firma == firma)
        rows = q.all()

        if firma is not None and not rows:
            print(f"No classification records for firma={firma!r}.")
            return

        for row in rows:
            new_type = row.company_type
            new_stage = row.company_stage

            # Fix 1: enterprise used as company_type (LLM confused type with stage)
            if row.company_type == "enterprise":
                new_type = "product"

            # Fix 2 & 3: web-verified correct company_type
            if row.firma in _TYPE_FIXES:
                new_type = _TYPE_FIXES[row.firma]

            # When type CHANGES TO public_sector, stage must also be public_sector
            if new_type == "public_sector" and row.company_type != "public_sector":
                new_stage = "public_sector"

            # TenneT was wrongly classified as public_sector/public_sector
            if row.firma == "TenneT TSO GmbH Unternehmensleitung":
                new_stage = "enterprise"

            if new_type != row.company_type or new_stage != row.company_stage:
                fixes.append(
                    (row, row.company_type, row.company_stage, new_type, new_stage)
                )

        if not fixes:
            print("No errors found.")
            return

        # Group by change for readable output
        by_change: dict[tuple, list[str]] = defaultdict(list)
        for row, old_t, old_s, new_t, new_s in fixes:
            by_change[(old_t, old_s, new_t, new_s)].append(row.firma)

        print(f"[{tag}] {len(fixes)} records to fix ({scope}):\n")
        for (old_t, old_s, new_t, new_s), firmas in sorted(by_change.items()):
            print(f"  {old_t}/{old_s}  →  {new_t}/{new_s}  ({len(firmas)} records)")
            for firma in sorted(set(firmas)):
                print(f"    {firma}")

        if apply:
            for row, _, _, new_t, new_s in fixes:
                row.company_type = new_t
                row.company_stage = new_s
            print("\n[APPLY] Done.")
        else:
            print("\nRun with --apply to write changes.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--firma",
        metavar="NAME",
        help="Only fix records with this exact firma string",
    )
    args = parser.parse_args()
    main(apply=args.apply, firma=args.firma)
