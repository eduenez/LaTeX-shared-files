## José Iovino's repositories: who delegates what

José Iovino delegates every backend aspect of LaTeX (packages, macros, fonts, templates, build, formatting, Git) to his agent, so
[Authors delegate the backend](#authors-delegate-the-backend-repair-the-right-way) applies here in full. When he asks for a
package, a font or a macro, it goes in the paper's `.sty` after checking the house base, never in the main `.tex` and never in
`_templates/`; report the change in one line and do not ask him to follow the conventions himself. The commit checks are
installed automatically by the build; if they are missing anyway, install them (`make install-hooks`) without a lesson.
(QuantumTeam commit 94263bf, which put `euscript` in three templates and a main file citing a nonexistent "STYLE.md, rule 24",
is the case this guards against.)

## Abstracts and introductions

These rules are José Iovino's and are binding for every assistant and every person working on an abstract or an introduction in
this repository, including a "literary pass" on one. Check the draft against every rule below before showing it to anyone.

**What an abstract is for.** It states, precisely and briefly, what *this* paper proves and how that improves on the specific
earlier result it builds on (for example, the 1967 theorem of Kochen and Specker).

- Name the earlier result and say exactly what the paper adds: a stronger conclusion, weaker hypotheses, a wider class of
  structures, a new kind of witness, or a new method.
- Never attribute the earlier theorem to the present paper ("we prove the Kochen–Specker theorem for …" is false).
- Use the word that matches the claim: a strengthening is not a "counterpart" or a "formulation".
- No vague gestures ("the whole of Gleason's setting"): name the structures.
- Name the method that replaces the classical one (for example, model-theoretic forcing, cast as a two-player topological game,
  in place of compactness).
- When the author already has an abstract, build on it: keep his sentences and change only what the request requires.
  If a length is requested ("two sentences"), deliver exactly that.

**What an introduction is for.** It is a continuous, erudite, precise narrative that leads from the earlier work to the
paper's results and says explicitly why those results are an improvement.

- No subheadings (except a closing "Organization of the paper"), no bullet or numbered lists in the text, no clipped
  sentences: a high literary register throughout.
- **Advanced literary register.** Write in the elevated, precise prose of a distinguished mathematical monograph. Never
  use childish, colloquial or lowbrow language: no chatty phrasing, no slang, no breezy intensifiers ("really",
  "basically", "just", "huge", "a bunch of"), no rhetorical questions, no exclamations, and no textbook-for-children
  explanations. Prefer exact, cultivated vocabulary and syntax that carries the logic of the argument. Every sentence
  should be one that a careful reader of the best mathematical writing would find natural and dignified.
  In particular, never append a limp pronoun sentence or clause to finish a thought ("He did so in …", "It does so by …",
  "They do so …"): integrate the information into the main sentence.
- **No ignorant language.** José Iovino does not want ignorant, uninformed or imprecise language of any kind: no loose
  paraphrase of a theorem, no misattribution, no vague or naive characterization of a field or a result, and no wording
  that betrays unfamiliarity with the literature. Every sentence must read as the work of an expert in the subject.
- **Do not belabor what every specialist knows** (for example, that ultraproducts destroy separability). Write for an expert reader.
- **Literary prose, neither run-on nor telegraphic.** Do not string clauses together with commas: a sentence with more than
  two commas, or a chain of subordinate clauses, must be recast. Equally, do not chop the text into short declarative
  sentences that read like a telegram. Write sentences of moderate length, joined by logical connectives (since, whereas,
  therefore, yet, for), so that each paragraph reads as one argument. This applies to abstracts, introductions and every
  literary pass.
- When the author gives an outline (for example, steps (1)–(6)), follow it in order, completely, as one argument, with no
  detours or repetitions. Check the draft against each step.
- Present earlier work in chronological order and verify the years.
- Describe each earlier result by what it established. Never disparage anyone's work ("falls silent", "could only
  guarantee", "nothing of …", "its scope is merely …"); frame differences as what the new result adds.
- State explicitly, for each main result, which earlier result it improves and in what precise respect.
- When the paper claims a finer notion (for example, finer finite obstructions), explain concretely why it is finer.
- Copy theorem statements verbatim from the paper. A literary pass changes phrasing, never claims.

**Process.** Start from the current text in the `.tex` file. Keep the author's sentences, mark what you changed and offer a
side-by-side comparison. Verify every claim about other people's work (who proved what, when, in what language) against the
sources, and flag what you could not verify. Get it right once, then deliver promptly: students may be waiting.
