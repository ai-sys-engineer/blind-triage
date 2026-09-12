BLINDED SYMPTOM (carried forward; the original report is now SEALED)
  observed : In the current working tree, the setting `max_ecr_loops` reads 9; the value
             carried in committed state is 3. The 9 is not in any commit — it exists only as
             an uncommitted working-tree modification. Report ID: F8.

  chosen because : It is the only present-tense, on-disk, directly checkable condition the
             report states, and it is the one thing the report was raised to get a decision
             about; the two run endings below are two different past events (one ended one
             way at 3, the other ended another way at 4) that would each need their own
             explanation, so they are not the same symptom as this one or as each other.

  runs     : 055902, 065833
             (both stamps come from the report; neither run is the observed item above —
             both attach to ALSO OBSERVED entries and are NOT scored by the Phase 4 ledger)

  ALSO OBSERVED (not the symptom; carried forward, NOT scored by the Phase 4 ledger):
    055902 deadlocked at 3.
    065833 ... was killed at 4.
    "Please note, we have already made fixes to the code base recently so this bug may very
     well have been impacted by the fixes post ledger of the bug. It may not even be relevant
     anymore, or it may still exist." (reporter's own note; the report predates recent
     changes to the tree, so any of the three observations above may no longer reproduce)

  NOT carried forward: (deleted mechanism/verdict wording — listed so the human can object)
    - The report's SITE LIST, deleted outright: one source file with a line number, plus one
      documentation file path. Phase 1 is not told where to look.
    - "used the raised budget" — a causal link asserted between the uncommitted value and how
      run 065833 ended. Struck from the 065833 line above, which is why that line reads with
      an ellipsis.
    - The title's framing that a value "raised 3 -> 9" is the thing that distinguishes the two
      runs — that is the report's hypothesis, compressed into something that reads like a
      finding.
    - "budget" as a characterization of the numeric setting.
    - "Status: Decision needed" — a verdict about what should happen next.
    - "Class: Housekeeping" — a pre-classification of severity/kind.
    - "Chronic?: n/a" and "Offline testable?: n/a" — report metadata carrying no observation.
    - KEPT DELIBERATELY, OBJECT IF WRONG: the identifier `max_ecr_loops` and the numbers
      3 / 9 / 4 are retained. The identifier is a value name the observation cannot be stated
      without, but it does point at machinery — if you want it blinded too, say so now and the
      observation becomes "a numeric limit in the working tree reads 9 where committed state
      says 3".
