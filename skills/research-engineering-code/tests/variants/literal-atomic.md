# Comparison variant: literal atomic decomposition

This is not a skill. It is the competing reading of "decompose into atomic functions, then write unit tests", kept so the evaluation can check the behaviour-and-interface decomposition in `SKILL.md` against it.

To build the variant, copy `SKILL.md`, change `name` to `research-engineering-code-atomic`, and make four changes:

- In section 1, replace the "Behaviours" line of the design with the "Functions" line below.
- In section 3, delete the "Behaviours, not fragments" bullet.
- Replace section 4 with the section below.
- In section 5, delete "Test through public interfaces," from the "Tests worth keeping" bullet.

Remove the links to both reference files, because they argue for the other approach.

---

Design line:

- **Functions**: break the work down until every function does exactly one thing and cannot sensibly be split further; list each with its signature.

## 4. Give every function its own unit tests, written first

Write unit tests for every function in the design, public or private, before implementing any of them. Each test exercises one function directly and in isolation, with stubs for its collaborators. Then implement the functions until every test passes.
