"""Build data/tau2/domains/web_support/tasks.json from the verified facts.

Each task is a customer calling "AnswerLine" with one practical question whose
answer sits on a public page. Facts were verified on 2026-10-09 (see
data/tau2/domains/web_support/facts/*.json). Rerun this script after
re-verifying facts; it also writes split_tasks.json (evergreen / changed).

Usage:  uv run python scripts/web_support/build_tasks.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "tau2" / "domains" / "web_support"
FACTS_DIR = DATA / "facts"

USER_TEMPLATE = """You are playing the role of a customer calling AnswerLine, a helpdesk that answers practical questions about companies and public services. You are on a voice call, so keep messages short and natural.

Your character: {persona}

Your question: {question}

Details you only share if the agent asks: {details}

You do not know the answer yourself and must not suggest or guess any figure. Once the agent gives you a specific figure for {target}, thank them and end the conversation by generating the token ###STOP###. If the agent gives only vague guidance without a specific figure, ask once for the exact number; if they still do not give one, end the conversation with ###STOP###. Do not ask any other questions. Never respond as the agent; you are the customer."""

# key -> scenario-specific fields. Facts (answers, sources) come from the facts files.
SCENARIOS: dict[str, dict] = {
    # ---------------- changed since 2025 ----------------
    "ryanair_small_bag": dict(
        persona="Priya, flying Ryanair from Stansted to Dublin next week with just a backpack.",
        question="How big can my free small bag be on Ryanair? The one that goes under the seat.",
        details="Flying from London Stansted to Dublin; you have not paid for priority or any extra bag.",
        target="the maximum dimensions of the free under-seat bag",
        nl=["The agent told the customer that Ryanair's free small personal bag may be up to 40 x 30 x 20 cm (the current size, not the older 40 x 25 x 20 or 40 x 20 x 25)."],
        comm=[],
    ),
    "uk_passport_renew_online": dict(
        persona="Tom, 41, whose adult UK passport expires in March and who wants to renew it online.",
        question="How much does it cost to renew my passport if I do it online?",
        details="Adult standard 34-page passport; applying online, not by paper form; standard service, not fast track.",
        target="the online renewal fee",
        nl=["The agent told the customer that renewing an adult UK passport online costs £102 (the fee since April 2026, not the older £94.50 or £88.50)."],
        comm=["102"],
    ),
    "delta_first_bag_fee": dict(
        persona="Marcus, booking a Delta Main Cabin flight from Atlanta to Denver today.",
        question="What will Delta charge me for my first checked bag?",
        details="US domestic flight, Main Cabin fare, no Delta status and no Delta credit card; buying the ticket today.",
        target="the first checked bag fee",
        nl=["The agent told the customer that Delta's first checked bag fee on a domestic Main Cabin ticket bought now is $45 each way (the fee since April 2026, not the older $35)."],
        comm=["45"],
    ),
    "fscs_limit": dict(
        persona="Helen, 58, who has just received an inheritance and wants to know how much is safe to keep in one UK bank.",
        question="How much of my money is protected by the FSCS if the bank goes under?",
        details="Sole account at a UK-authorised bank; not a joint account.",
        target="the FSCS protection limit per person per bank",
        nl=["The agent told the customer that the FSCS deposit protection limit is £120,000 per person per authorised firm (the limit since 1 December 2025, not the old £85,000)."],
        comm=["120000"],
    ),
    "wise_atm": dict(
        persona="Lena, a UK Wise card holder heading to Portugal for two weeks.",
        question="How much can I take out of cash machines each month with my Wise card without a fee, and what do they charge after that?",
        details="UK-issued Wise personal card; you want the standard monthly allowance, not a business account.",
        target="the free monthly ATM allowance and the fee above it",
        nl=["The agent told the customer that the UK Wise card allows free ATM withdrawals up to £250 per month, and that above that a 2.69% fee applies (current terms, not the older £200 / 1.75% plus 50p terms)."],
        comm=["250", "2.69"],
    ),
    "costco_uk_membership": dict(
        persona="Daniel, who wants to join Costco in the UK as an ordinary individual member.",
        question="How much is a Costco membership for an individual in the UK?",
        details="Individual (Gold Star) membership, not a business/trade membership and not Executive; you want the price including VAT.",
        target="the annual individual membership fee",
        nl=["The agent told the customer that Costco UK individual (Gold Star) membership costs £42 per year including VAT (or £35 excluding VAT), the current price rather than the older £33.60 / £28."],
        comm=["42"],
    ),
    "royal_mail_first_class": dict(
        persona="Margaret, 72, posting birthday cards and unsure what stamps cost now.",
        question="How much is a first class stamp at the moment? And a second class one?",
        details="Standard letters, posted within the UK.",
        target="the current 1st and 2nd class stamp prices",
        nl=["The agent told the customer that a Royal Mail 1st Class standard letter stamp costs £1.80 and a 2nd Class stamp costs 91p (prices since April 2026, not the older £1.70 / 87p)."],
        comm=["1.80", "91"],
    ),
    "london_congestion_charge": dict(
        persona="Ahmed, driving a petrol car into central London on a weekday for the first time this year.",
        question="How much is the Congestion Charge per day now? I'll pay in advance.",
        details="Petrol car, not electric; paying in advance or on the day, not late; weekday daytime.",
        target="the daily Congestion Charge",
        nl=["The agent told the customer that the London Congestion Charge is £18 per day when paid in advance or on the day (the rate since 2 January 2026, not the older £15)."],
        comm=["18"],
    ),
    "tv_licence": dict(
        persona="Sophie, who has just moved into her first flat and needs a TV licence.",
        question="How much is a TV licence for a year?",
        details="Standard colour licence, paying for the full year, no concessions.",
        target="the annual TV licence fee",
        nl=["The agent told the customer that a colour TV licence costs £180 per year (the fee since 1 April 2026, not the older £174.50 or £169.50)."],
        comm=["180"],
    ),
    "netflix_uk_standard": dict(
        persona="Jake, comparing streaming subscriptions in the UK.",
        question="What does Netflix Standard cost a month now, and what's the cheaper plan with adverts?",
        details="UK account; you want the Standard plan and the Standard with adverts plan, not Premium.",
        target="the monthly price of Standard and of Standard with adverts",
        nl=["The agent told the customer that Netflix UK Standard costs £13.99 per month and Standard with adverts costs £7.99 per month (prices since September 2026, not the older £12.99 / £5.99)."],
        comm=["13.99", "7.99"],
    ),
    # ---------------- evergreen ----------------
    "easyjet_large_cabin": dict(
        persona="Chloe, flying easyJet from Gatwick to Barcelona with a wheelie suitcase.",
        question="What's the biggest cabin bag I can take on easyJet, and is it included in a normal ticket?",
        details="Standard fare, no easyJet Plus membership, not an Up Front or Extra Legroom seat.",
        target="the large cabin bag maximum dimensions and whether it is included",
        nl=["The agent told the customer that easyJet's large cabin bag may be up to 56 x 45 x 25 cm and that it is a paid extra on a standard fare (only the small under-seat bag is free)."],
        comm=[],
    ),
    "ba_checked_weight": dict(
        persona="Rohan, flying British Airways economy from Heathrow to Mumbai with one suitcase.",
        question="What's the maximum weight for my checked bag in economy on BA?",
        details="Economy (World Traveller) fare that includes a checked bag; no frequent flyer status.",
        target="the maximum weight per checked bag",
        nl=["The agent told the customer that British Airways allows up to 23 kg per checked bag in economy."],
        comm=["23"],
    ),
    "tsa_liquids": dict(
        persona="Emily, flying from Chicago O'Hare with carry-on only and a bag of toiletries.",
        question="How big can my liquid containers be in my carry-on through US security?",
        details="Domestic US flight; ordinary toiletries, nothing medical.",
        target="the maximum container size for liquids",
        nl=["The agent told the customer that each liquid container in a US carry-on must be 3.4 oz (100 ml) or less under the TSA 3-1-1 rule."],
        comm=["3.4"],
    ),
    "costco_us_gold_star": dict(
        persona="Carlos, in Texas, thinking about joining Costco.",
        question="How much is the basic Costco membership in the US per year?",
        details="Gold Star (basic individual) membership, not Executive and not Business.",
        target="the annual Gold Star membership fee",
        nl=["The agent told the customer that a Costco US Gold Star membership costs $65 per year."],
        comm=["65"],
    ),
    "section75": dict(
        persona="Grace, who paid a £2,000 deposit for a kitchen on her credit card and the company has gone bust.",
        question="Does Section 75 cover me, and what's the price range it applies to?",
        details="UK credit card; the kitchen's total price was £9,000 and you paid £2,000 of it on the card.",
        target="the minimum and maximum item price covered by Section 75",
        nl=["The agent told the customer that Section 75 applies to items costing more than £100 and up to £30,000 (both bounds stated)."],
        comm=["100", "30000"],
    ),
    "paypal_buyer_protection_window": dict(
        persona="Ben, who paid for a guitar with PayPal six weeks ago and it has never arrived.",
        question="How long have I got to open a dispute with PayPal for an item that never arrived?",
        details="UK PayPal account; paid six weeks ago; the seller has stopped replying.",
        target="the number of days to open an item-not-received dispute",
        nl=["The agent told the customer that a PayPal item-not-received dispute must be opened within 180 days of the payment, so six weeks is well within the window."],
        comm=["180"],
    ),
    "monzo_atm_abroad": dict(
        persona="Aisha, with a free Monzo account, travelling to Morocco for ten days.",
        question="How much cash can I withdraw abroad on Monzo before they charge me, and what's the fee after that?",
        details="Free personal Monzo account (not Plus/Premium); Morocco is outside the EEA; Monzo is not your main bank account.",
        target="the fee-free withdrawal allowance and the fee above it",
        nl=["The agent told the customer that on a free Monzo account they can withdraw £200 fee-free every 30 days outside the UK/EEA, after which a 3% fee applies."],
        comm=["200", "3%"],
    ),
    "nhs_prescription_england": dict(
        persona="Oliver, in Manchester, newly prescribed two monthly medicines.",
        question="How much does an NHS prescription cost per item in England, and how much is the 12-month prepayment certificate?",
        details="You live in England, are 35, and have no exemption.",
        target="the per-item charge and the 12-month certificate price",
        nl=["The agent told the customer that an NHS prescription in England costs £9.90 per item and a 12-month prepayment certificate costs £114.50."],
        comm=["9.90", "114.50"],
    ),
    "ikea_uk_returns": dict(
        persona="Natalie, who bought a bookcase from IKEA in the UK four months ago and never opened the box.",
        question="How long do I have to return something to IKEA?",
        details="Bought in store in the UK; still unopened; you have the receipt.",
        target="the returns window in days",
        nl=["The agent told the customer that IKEA UK accepts returns within 365 days, so a four-month-old unopened purchase can still be returned."],
        comm=["365"],
    ),
    "ofcom_text_to_switch": dict(
        persona="Sam, who wants to move their mobile number from one UK network to another.",
        question="How do I get the code to move my number to a new network, and how long is it valid for?",
        details="UK pay-monthly mobile; you want to keep your number.",
        target="the number to text and the validity period of the PAC",
        nl=["The agent told the customer to text PAC to 65075 to get their PAC code and that the code is valid for 30 days."],
        comm=["65075", "30"],
    ),
}

CHANGED = [
    "ryanair_small_bag",
    "uk_passport_renew_online",
    "delta_first_bag_fee",
    "fscs_limit",
    "wise_atm",
    "costco_uk_membership",
    "royal_mail_first_class",
    "london_congestion_charge",
    "tv_licence",
    "netflix_uk_standard",
]
EVERGREEN = [
    "easyjet_large_cabin",
    "ba_checked_weight",
    "tsa_liquids",
    "costco_us_gold_star",
    "section75",
    "paypal_buyer_protection_window",
    "monzo_atm_abroad",
    "nhs_prescription_england",
    "ikea_uk_returns",
    "ofcom_text_to_switch",
]


def load_facts() -> dict[str, dict]:
    facts: dict[str, dict] = {}
    for p in sorted(FACTS_DIR.glob("batch_*.json")):
        for f in json.loads(p.read_text()):
            facts[f["key"]] = f
    return facts


def main() -> None:
    facts = load_facts()
    tasks = []
    splits = {"changed": [], "evergreen": []}
    for i, key in enumerate(CHANGED + EVERGREEN, 1):
        sc = SCENARIOS[key]
        fact = facts[key]
        split = "changed" if key in CHANGED else "evergreen"
        task_id = f"ws_{i:03d}_{key}"
        splits[split].append(task_id)
        notes = (
            f"split={split}; verified_on={fact['verified_on']}; stability={fact['stability']}; "
            f"confidence={fact['confidence']}; previous_value={fact.get('previous_value')}"
        )
        tasks.append(
            {
                "id": task_id,
                "description": {
                    "purpose": f"Customer asks: {sc['question']} Expected: {fact['answer_current']}",
                    "relevant_policies": f"Source: {fact['source_title']} ({fact['source_url']})",
                    "notes": notes,
                },
                "user_scenario": {
                    "persona": None,
                    "instructions": USER_TEMPLATE.format(
                        persona=sc["persona"],
                        question=sc["question"],
                        details=sc["details"],
                        target=sc["target"],
                    ),
                },
                "initial_state": None,
                "evaluation_criteria": {
                    "actions": [],
                    "communicate_info": sc["comm"],
                    "nl_assertions": sc["nl"],
                    "reward_basis": ["NL_ASSERTION"],
                },
                "user_tools": [],
            }
        )
    (DATA / "tasks.json").write_text(json.dumps(tasks, indent=2, ensure_ascii=False) + "\n")
    splits["base"] = splits["changed"] + splits["evergreen"]  # tau2 default split name
    (DATA / "split_tasks.json").write_text(json.dumps(splits, indent=2) + "\n")
    print(f"wrote {len(tasks)} tasks: {len(splits['changed'])} changed, {len(splits['evergreen'])} evergreen")


if __name__ == "__main__":
    main()
