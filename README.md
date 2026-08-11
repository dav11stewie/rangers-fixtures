# Rangers Fixtures

A free, self-updating web app showing every Glasgow Rangers FC fixture for the
year, with UK TV channel info where known. Installs to your iPhone home
screen like a native app.

- **Fixtures** come from BBC Sport (all competitions, whole season).
- **TV channels** come from [live-footballontv.com](https://www.live-footballontv.com/rangers-on-tv.html)
  (only covers currently-known upcoming televised games).
- A GitHub Actions robot re-runs the scraper 3x a day and commits any
  changes, so the site updates itself with zero maintenance.
- Hosting is GitHub Pages — free, no server to manage.

Total cost: **£0**.

---

## One-time setup (do this once, ~15 minutes)

You'll need a terminal (already open, since you're reading this) and a web
browser.

### 1. Create a GitHub account

If you don't have one already: go to [github.com/signup](https://github.com/signup)
and create a free account.

### 2. Create a new repository

1. Go to [github.com/new](https://github.com/new).
2. Repository name: `rangers-fixtures` (or anything you like).
3. Set it to **Public** — GitHub Pages requires a public repo on the free tier.
4. **Do not** check "Add a README file" — this project already has one.
5. Click **Create repository**. Leave the resulting "quick setup" page open;
   you'll need the URL shown there:
   `https://github.com/dav11stewie/rangers-fixtures.git`.

### 3. Create a Personal Access Token (needed to push from your terminal)

GitHub no longer accepts your account password for `git push` over HTTPS.

1. Go to [github.com/settings/tokens](https://github.com/settings/tokens) →
   **Generate new token** → **Generate new token (classic)**.
2. Give it a name like `rangers-fixtures-push`, expiration of your choice.
3. Tick the **repo** scope checkbox (this grants push access).
4. Click **Generate token** and **copy it somewhere safe now** — GitHub only
   shows it once.

### 4. Push this project to GitHub

In your terminal:

```bash
cd /Users/ddstewart/rangers-fixtures
git init
git add .
git commit -m "Initial commit: Rangers fixtures app"
git branch -M main
git remote add origin https://github.com/dav11stewie/rangers-fixtures.git
git push -u origin main
```

When it asks for a username, enter your GitHub username. When it asks for a
password, **paste the Personal Access Token** from step 3 (not your account
password).

### 5. Let the robot push updates

1. On your repo's GitHub page, go to **Settings → Actions → General**.
2. Scroll to **Workflow permissions**.
3. Select **Read and write permissions**.
4. Click **Save**.

(Without this step, the scheduled job will run but fail to `git push` its
updates — you'd see a red ❌ in the Actions tab.)

### 6. Turn on GitHub Pages

1. Go to **Settings → Pages**.
2. Under **Build and deployment → Source**, choose **Deploy from a branch**.
3. Branch: `main`, folder: `/ (root)`. Click **Save**.
4. Wait ~1 minute, then refresh the page — it will show your live URL:
   `https://dav11stewie.github.io/rangers-fixtures/`

### 7. Run the scraper once to seed real data

The repo already includes a `data/fixtures.json` you generated locally, so
this step is optional — but it confirms the automation works end to end:

1. Go to the **Actions** tab on your repo.
2. You may see a banner asking to confirm workflows — click to enable them.
3. Click **Update fixtures** in the left sidebar, then **Run workflow** →
   **Run workflow** (green button).
4. Wait ~30 seconds, refresh — you should see a green checkmark.

From now on, this runs automatically 3 times a day. You never need to touch
it again.

### 8. Add it to your iPhone home screen

1. On your iPhone, open **Safari** (must be Safari, not Chrome — only Safari
   can install web apps on iOS) and go to your Pages URL from step 6.
2. Tap the **Share** icon (square with an arrow) → **Add to Home Screen**.
3. Tap **Add**. You now have a "Rangers" icon on your home screen that opens
   full-screen, like a real app.

---

## Testing changes locally before pushing

```bash
cd /Users/ddstewart/rangers-fixtures

# Re-run the scraper (see note below about SSL on this Mac):
SSL_CERT_FILE=/private/etc/ssl/cert.pem python3 scripts/update_fixtures.py --verbose

# Preview in a browser:
python3 -m http.server 8000
# then open http://localhost:8000 in your browser
```

### Note: SSL certificate error on this Mac

This Mac's Python 3.14 install has an empty certificate store, so running
the scraper directly gives `CERTIFICATE_VERIFY_FAILED`. Two fixes:

- **Quick (per command):** prefix with `SSL_CERT_FILE=/private/etc/ssl/cert.pem`,
  as shown above.
- **Permanent:** open `/Applications/Python 3.14/Install Certificates.command`
  (double-click it in Finder) once.

This only affects running the scraper *on this Mac*. GitHub Actions' runners
already have valid certificates, so the scheduled job is unaffected.

---

## How it works

```
scripts/update_fixtures.py   -- fetches + merges fixture & TV data
        │
        ▼
data/fixtures.json           -- the only file the frontend reads
        │
        ▼
index.html / app.js / styles.css   -- renders the fixture list
manifest.webmanifest / sw.js       -- makes it installable + offline-capable
```

`update_fixtures.py`:
1. Pulls every Rangers first-team fixture for the year from BBC Sport's
   fixtures JSON endpoint (12 requests, one per month).
2. Pulls current UK TV channel listings from live-footballontv.com.
3. Matches them up by date + opponent name (handling spelling differences
   like "St. Mirren" vs "St Mirren", or accented names like "Białystok").
4. Writes `data/fixtures.json`. Refuses to overwrite good data with an
   empty/partial result if either site fails.

`.github/workflows/update-fixtures.yml` runs that script 3x/day and commits
`data/fixtures.json` if it changed.

## If something breaks

Both data sources are websites, not official APIs, so either could change
its page structure and break the scraper. If that happens:

- Check the **Actions** tab — a failed run shows a red ❌ with the error.
- The site will keep showing the last successfully-fetched data; a scraper
  failure never wipes out good data.
- Re-run `scripts/update_fixtures.py --verbose` locally to see what broke.

Regenerating the placeholder icons (if you ever want to): run
`python3 scripts/make_icons.py`.
