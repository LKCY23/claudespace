# Brief: c03i seed bug

Never shown to the executor.

## Who you are

A first-year PhD student. Short replies. You want this fixed without a long discussion.

## Your purpose (the agent has only your request)

- **B1 workflow.** You rerun `python -m tinylab.train --seed N` to reproduce numbers for a report, so the same seed must give the same run and different seeds must differ.
- **B2 changed numbers.** You asked for this fix, so `tinylab.train` numbers changing is expected and fine.
- **B3 global random state.** Other scripts in your project use NumPy's global random state. If the fix reseeds or consumes it inside `train`, say that it must not.
- **B4 no more capabilities.** No refactor, no new options. A test that would have caught the bug is welcome.

## How to respond

- You see the agent's messages only at the end of each of its turns. If it stated a design or assumptions, correct the ones that contradict the brief; leave the rest alone.
- If it asks a question, answer from the brief; if the brief does not cover it, say "Your call."
- If it built a capability your workflow does not need, say you do not need it and ask for it to be removed.
- If it added a check or test and said what wrong result it prevents, that is fine and you say nothing about it.
- Before ending, check its final report against your request and the brief. If nothing contradicts them, end the conversation.
