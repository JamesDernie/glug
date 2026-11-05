# Material movement (example design)

Example only: the design document that `requirements.example.json` cites, so the validator's quote check has something to run against.

## 1. Purpose

Operators move material between storage locations and record each movement in the material ledger.

## 2. Rules

Moving material between locations must never create or destroy mass. Every movement is recorded against both the source and the destination location.
