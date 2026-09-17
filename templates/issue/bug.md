---
name: Bug
about: Something is broken — behavior diverges from what's expected.
title: "fix: "
labels: type:bug
---

## Description

<!-- One or two sentences: what's wrong and where. Name the component, not
     just the symptom.
     Example: "The CSV export drops rows whose `notes` field contains a
     comma — the column count shifts and every field after `notes` is
     misaligned." -->

## Steps to Reproduce

<!-- Concrete and minimal — someone unfamiliar with the code should be able
     to follow these and hit the bug on the first try.
     Example:
     1. Create an invoice with a note containing a comma, e.g. "call, then invoice"
     2. Export invoices to CSV from the Invoices page
     3. Open the file — the row's fields after `notes` are shifted left by one column -->

1.
2.
3.

## Expected vs. Actual

<!-- Two short statements, not a paragraph.
     Example:
     Expected: the `notes` field is quoted in the CSV so the comma doesn't
     break the column count.
     Actual: the field is written unquoted, splitting it into two columns. -->

## Impact

<!-- Who hits this, how often, and how bad it is when they do — not
     "important," give the shape of the damage.
     Example: "Every export containing a note with a comma is affected;
     finance re-imports these into their own tooling weekly, so this
     silently corrupts a recurring report." -->
