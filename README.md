# Chatham Park Grocery Watcher

A small robot that checks the web every morning and emails you when there is news about which grocery chain is coming to the new mixed-use center near the Chatham Park YMCA in Pittsboro, NC. It runs free on GitHub Actions, so no computer needs to stay on.

It was built for one question in one town, but every keyword and source lives in `config.yaml`. To watch for something else (a new restaurant, a rezoning, a school site), see [Adapting it to track something else](#adapting-it-to-track-something-else).

## What it checks

| Source | How |
|---|---|
| Google News | About 20 searches, such as `"Chatham Park" grocery`, `Pittsboro grocery store`, and one per chain (`"Chatham Park" Publix`, `"Chatham Park" Harris Teeter`, and so on) |
| Local news | Chatham News + Record, Chapelboro, and Chatham Journal feeds, plus Google News searches limited to each of those sites (a backup if a site's own feed breaks) |
| Town of Pittsboro agendas | The town's CivicPlus Agenda Center (pittsboronc.gov/AgendaCenter). It finds Board of Commissioners and Planning Board meetings, downloads the full agenda packet PDF, and searches the text. Site plans often name a tenant before any press release. |

An item is flagged only if it mentions a **place** (Chatham Park, Pittsboro, Mosaic, YMCA, South Village, North Village) **and** a **grocery term** (grocery, supermarket, anchor tenant, or a chain name).

Stories that are only about the existing Lowes Foods at Northwood Landing are marked **lower priority**. They never trigger an email by themselves. They ride along at the bottom of the next real alert or weekly heartbeat.

## What the email looks like

Subject: **Chatham Park grocery watch: 3 new mentions**

Each mention shows the headline (linked), source, date, which keywords matched, and the matching passage with keywords highlighted. Some news items say "Headline only": Google News found the grocery mention inside the article, but only shares the headline, so open the link to read it. At the bottom, a one-line health check says how many sources worked, and names any that failed.

If nothing new turned up, no email is sent. Once a week (Monday by default) you get a short "no new mentions this week" email so you know it is still running. You can turn that off.

## Setup (about 15 minutes, no coding)

The watcher's settings are in `config.yaml`, and its schedule is in `.github/workflows/watch.yml`. GitHub only runs scheduled jobs from the repository's `main` branch.

### Step 0. Make your own copy

You need a free GitHub account. Your copy holds your own email settings, so nothing you set up touches this repository.

1. At the top of this repository's page, click **Fork**, then **Create fork**.
2. In your fork, open `seen.json`, click the trash icon, and commit. That file is the original owner's memory of what was already sent. Without this step, your first run would skip everything they have already seen. The watcher creates a fresh one for you on its first run.
3. Open the **Actions** tab of your fork and click **I understand my workflows, go ahead and enable them**. GitHub turns off scheduled jobs in forks until you do this.

### Step 1. Get a Gmail app password

Gmail will not let a program use your normal password. You create a separate 16-character "app password" for this one purpose.

1. Go to [myaccount.google.com/security](https://myaccount.google.com/security).
2. Under "How you sign in to Google", turn on **2-Step Verification** if it is not already on. App passwords require it.
3. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords).
4. Type a name such as `Grocery watcher` and click **Create**.
5. Copy the 16-letter password Google shows you. You will paste it in Step 2. (Spaces in it are fine.)

You can revoke it from the same page at any time without affecting your normal Gmail password.

### Step 2. Add your secrets to GitHub

Secrets are stored encrypted by GitHub. They never appear in the code or the logs.

1. On GitHub, open this repository and click **Settings** (top right of the repo page).
2. In the left menu, click **Secrets and variables**, then **Actions**.
3. Click **New repository secret** and add each of these:

| Name | Value |
|---|---|
| `SMTP_USER` | Your Gmail address, for example `you@gmail.com` |
| `SMTP_PASSWORD` | The app password from Step 1 |
| `EMAIL_TO` | Where alerts go. Can be the same address. For several people, separate with commas. Optional: defaults to `SMTP_USER`. |

### Step 3. Allow the robot to save its memory

The watcher remembers what it already sent by saving a small file (`seen.json`) back into the repository after each run.

1. **Settings**, then **Actions**, then **General**.
2. Scroll to **Workflow permissions**, choose **Read and write permissions**, and click **Save**.

### Step 4. Test it

Go to the **Actions** tab, click **Chatham Park grocery watch** in the left list, then **Run workflow**. A menu lets you pick a mode. Run them in this order:

1. **check-sources**. Confirms each source can be reached. Open the run, click the `watch` job, and read the `Run watcher` step. Every line starts with `OK` or `FAIL`.
2. **test-email**. Sends you a one-line test email. If this fails, recheck the secrets in Step 2.
3. **dry-run**. Finds matches and prints the digest in the log, but sends nothing and remembers nothing. Use this any time you change keywords.
4. **normal**. The real thing. You should receive a digest of recent mentions.
5. **normal** again, right away. You should receive nothing, because those items were already sent.

After that, it runs by itself every morning.

## Changing the schedule

Open `.github/workflows/watch.yml` on GitHub and click the pencil icon. Find this line:

```yaml
    - cron: "17 11 * * *"
```

The first number is the minute and the second is the hour, in UTC. `17 11` means 7:17am Eastern in summer and 6:17am in winter.

| You want | Change the line to |
|---|---|
| Daily, about 7am Eastern | `- cron: "17 11 * * *"` (the default) |
| Weekly, Monday morning | `- cron: "17 11 * * 1"` |
| Twice a week, Monday and Thursday | `- cron: "17 11 * * 1,4"` |
| Daily, about 9pm Eastern | `- cron: "17 1 * * *"` |

Click **Commit changes**.

**Expect the email later than the scheduled time.** GitHub treats the schedule as "no earlier than," not an appointment. Runs often start late, sometimes by several hours on busy days. Keep the minute off `00`: so many jobs worldwide are scheduled on the hour that those wait longest. If the exact time matters to you, schedule it earlier than you need it.

To turn the weekly "nothing new" email off, or move it to a different day, edit `weekly_heartbeat` and `heartbeat_day` at the bottom of `config.yaml`.

## Editing keywords and sources

Everything the watcher looks for is in `config.yaml`. Open it on GitHub, click the pencil icon, edit, and commit. Each section has a short note explaining it. Common edits:

- **Add a chain:** add a line under `grocery_chains`, for example `  - Costco`. Keep the two spaces and the dash. A Google News search for `"Chatham Park" Costco` is added automatically.
- **Add a place:** add a line under `location_terms`.
- **Add a search:** add a line under `google_news: queries:`. Wrap exact phrases in single quotes on the outside and double quotes inside, like `'"Chatham Park" retail'`.
- **Look further back:** raise `max_age_days`.
- **Scan more town boards:** add a word from the board's name under `town_agendas: boards:`, or empty the list to scan every board.

After editing, run the workflow in **dry-run** mode to check the result before the next real run.

Matching ignores capitals and small spelling differences: `Lowe's Foods` matches `Lowes Foods`, `Trader Joes` matches `Trader Joe's`, and plurals match.

## Adapting it to track something else

The watcher asks one question: did anything mention **a place** and **a topic** together? Change the two lists and the searches, and it watches for something else. Make these edits in `config.yaml`, then run **dry-run** to see what the new settings would catch.

### Start with the question, then pick the words

Write down the one thing you are waiting to learn, for example "which restaurant takes the old bank building on Main Street." Then fill in:

| Setting | What goes in it | Example |
|---|---|---|
| `location_terms` | Names specific to your place: the development, the street, the neighborhood | `Main Street`, `Old Bank Building` |
| `grocery_terms` | Words that mean your topic (the name is historical; it works for any topic) | `restaurant`, `tenant`, `lease` |
| `grocery_chains` | Specific names you expect to see. These count as topic words too | `Chipotle`, `Panera` |
| `low_priority_terms` | Old news that keeps resurfacing and should not trigger an email alone | The tenant that already opened last year |
| `new_store_phrases` | Phrases that mean "this is new," which override low priority | `new location`, `coming soon` |

### Tips for better searches

1. **Specific beats broad.** Every location term must appear in an item before it can match. A city name alone will flood you; a development or street name will not. Put broad names in a search query instead, where Google does the filtering.
2. **Quote exact phrases.** `'"Main Street" restaurant'` finds the phrase; `Main Street restaurant` finds pages with those words anywhere. Keep the single quotes outside and double quotes inside.
3. **One idea per search.** Several short searches catch more than one long one. Google News returns only about 100 results per search.
4. **Back up each local outlet.** Add a `site:` search for each local paper (for example `'"Main Street" site:yourpaper.com'`). If the paper's own feed breaks, Google News still covers it.
5. **Turn off the automatic chain searches.** `add_chain_queries: true` builds one search per name in the form `"Chatham Park" <name>`, with Chatham Park built in. For another place, set it to `false` and write those searches yourself under `queries:`.
6. **Hold old news down, not out.** Rather than deleting a term that keeps matching stale stories, put it in `low_priority_terms`. You still see it, at the bottom of a real digest, and it never pages you alone.

### Swapping the sources

- **Local news feeds.** Most news sites built on WordPress publish a feed at `/feed/`. Add the site under `local_feeds` and run **check-sources** to confirm it works.
- **Town agendas.** This part reads only the CivicPlus "Agenda Center," which many US towns use. Your town uses it if its agenda page address contains `/AgendaCenter`. If so, change `base_url` to your town's site. If not, set `enabled: false`. The other sources keep working.
- **Email wording.** Change `subject_prefix` under `email:` so the subject names your topic.

## Using Resend instead of Gmail (optional)

1. Create a free account at [resend.com](https://resend.com) and create an API key.
2. Add the secret `RESEND_API_KEY`, and `EMAIL_TO`.
3. In `config.yaml`, change `provider: gmail` to `provider: resend`.

Without a verified domain, Resend only delivers to the email address on your Resend account. To send from your own domain, verify it in Resend and add an `EMAIL_FROM` secret such as `Grocery Watch <alerts@yourdomain.com>`.

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| Run shows a red X with "Missing secret" | A secret name is misspelled or missing. Names must match Step 2 exactly. |
| `Username and Password not accepted` | Use the app password, not your Gmail password, and confirm 2-Step Verification is on. |
| Run is green but has a yellow warning | One or more sources failed and the rest ran normally. The email footer and the log name the failed source. A site being down for a day is normal. If one fails every day, its address probably changed: update its URL in `config.yaml`. |
| "Save memory" step fails with `permission denied` | Step 3 was skipped. |
| Same item emailed twice | Usually the same story under two different headlines and links. Rare, and harmless. |

## Running it on your own computer (optional)

```bash
pip install -r requirements.txt
python watcher.py --check-sources
python watcher.py --dry-run
python -m unittest test_watcher -v   # offline tests, no network needed
```

To send real email locally, set `SMTP_USER`, `SMTP_PASSWORD`, and `EMAIL_TO` as environment variables first.

## Known limits

- Google News gives only a headline, so the watcher trusts Google's own search of the full article: if a search with a grocery word found a story whose headline names Chatham Park or Pittsboro, it is included and marked "Headline only". A story whose headline names neither place can still be missed. The chain-specific searches reduce this risk.
- Agenda packets that are scanned images (no selectable text) cannot be searched. Most Pittsboro packets are text PDFs.
- Packets over 60 MB are skipped so a single giant file cannot stall a run. Change `max_file_mb` in `config.yaml` to raise the limit.
