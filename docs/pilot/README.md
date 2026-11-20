# OntoPoc pilot kit

A kit for a 3 to 8 person team (ops, finance, data) to run a 2-week pilot of self-hosted OntoPoc. The question the pilot answers: when the team writes down what its numbers and status codes mean, does OntoPoc catch the wrong number and refuse instead of answering quietly wrong?

| File | What it is |
|---|---|
| [QUICKSTART.md](QUICKSTART.md) / [QUICKSTART.zh.md](QUICKSTART.zh.md) | One page: install, add teammates and roles, optional model key, where data lives, backups |
| [FIRST_DEFINITION.md](FIRST_DEFINITION.md) | Walkthrough of your first confirmed definition, from upload to a refusal after the data changes |
| [sample/](sample/) | Synthetic data (`customers.csv`, `orders.csv`, `order_status_notes.csv`, `orders_update.csv`), `make_sample.py` (fixed seed) and `expected_numbers.txt` |
| [QUESTION_LOG.csv](QUESTION_LOG.csv) | Everyone logs each question they ask: what they expected, what OntoPoc said, and whether it was right, wrong or refused (and whether a refusal was for a good reason) |

## Schedule

| Day | What happens |
|---|---|
| **Day 0, kickoff (60 min)** | Install and start. Admin adds everyone; at least two Builders. Run FIRST_DEFINITION.md together on the sample data. Each Builder picks one real table (10 MB limit per upload) and one question they currently answer by hand |
| **Days 1 to 4** | Builders upload their real table, define the object type and the code columns, and confirm each other's work. Everyone logs questions in QUESTION_LOG.csv, with the expected number computed outside OntoPoc **before** asking |
| **Day 5, check-in (30 min)** | Count the log: how many right, wrong, refused. Read every `wrong` and every refusal with `refusal_reason_ok` = n. What blocked people? Send feedback with the in-app link for anything that confused you |
| **Days 6 to 12** | Upload a fresh version of a real table at least once and note which definitions went back to "Needs review" and whether that was right. Add the questions you actually need answered this week |
| **Day 13, exit questions (30 min)** | See below. Back up `workspace.sqlite` and `sources.key` before deciding anything |

## Day 13 exit questions

Ask each person separately, then compare:

1. **If OntoPoc were gone tomorrow, would you be disappointed?** (Very / somewhat / not.) What would you go back to doing?
2. **What would you pay per month for it**, for your team? A number, even a rough one, and what it would have to do for that.
3. **Who else should try it?** Name the person or team, and the first question they would ask.

Builders and admins also see **Team questions, last 7 days** at the bottom of Home: how many questions were asked, answered, held back by a check (most often a definition that is not confirmed), or not worked out, and which unconfirmed definitions held back the most. It counts everyone's questions and shows no question text and no name. In a team of three or four, a builder who watches the counts can still guess who asked about a definition, so tell the team the counts exist. It cannot tell whether an answer was right; the log does that.

Also read off the log: the share of answers that matched, the number of wrong answers caught before anyone relied on them, and the share of refusals that were for a good reason.

## Rules of the pilot

- The model key is optional; set it only in the terminal that starts the service.
- Never put real customer personal data in the sample; use your own tables only after your team agrees that is acceptable on this machine.
- Everything stays on the machine running the service; see the privacy section of [README.en.md](../../README.en.md).
