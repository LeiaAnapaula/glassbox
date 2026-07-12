# Glassbox synthetic safeguarding-triage demo

This is a bounded hackathon demonstration of restraint in a high-stakes workflow.
It does **not** detect trafficking, identify victims or perpetrators, score people,
or report anything externally. Holo3.1 quotes observable statements from a
watermarked fictional screenshot, records missing context, and pauses before a
human decides whether to add the fictional case to a local review log.

## Run

```bash
cd agent
python3 -m pip install .
glassbox-triage-demo demo/synthetic-triage/case-01-document-control.png
```

The command refuses images without an adjacent `.synthetic.json` manifest that
explicitly declares `synthetic: true`. The decision log stays locally at
`~/.snapcal/synthetic-triage-log.jsonl`; every record sets `external_route` to
`null`.

Three fictional cases are provided:

- `case-01-document-control.png`: direct statements about document control,
  movement restriction, and wanting private support.
- `case-02-benign-job-offer.png`: a negative control demonstrating that a job
  offer alone must not be treated as a concern.
- `case-03-withheld-pay-threat.png`: direct statements about withheld pay, debt,
  and a threat after asking to leave.

## Guardrails

- No real-person screenshots or data.
- No accusation, identity inference, credibility assessment, or protected-trait inference.
- No single “risk score”; confidence refers only to extraction confidence.
- Every observation includes a verbatim quote and missing-context list.
- A deterministic post-validator drops category assignments unless the quote
  itself contains an adverse assertion; protective language cannot trigger review.
- No scraping, tracking, deanonymization, face recognition, or external reporting.
- A trained human sees the original material and makes the only disposition.

The framing follows two important cautions from authoritative sources:

- DHS Blue Campaign says the presence or absence of indicators is not proof and
  emphasizes appropriate, victim-centered response.
- Polaris's “Know the Story, Not the Signs” warns that signs without context are
  not meaningful identifiers of trafficking.

Sources:

- <https://www.dhs.gov/blue-campaign>
- <https://www.dhs.gov/sites/default/files/publications/blue-campaign/materials/pamphlet-victim-id-ngo-and-faith-based/bc-pamphlet-victim-id-ngo-english.pdf>
- <https://polarisproject.org/know-the-story-not-the-signs/>
