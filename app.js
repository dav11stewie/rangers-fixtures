// Rangers Fixtures -- vanilla JS, no build step, no dependencies.
// Renders data/fixtures.json into the page. All content is inserted via
// textContent (never innerHTML) so scraped team/competition names can't
// inject markup.

const DATA_URL = "data/fixtures.json";

function $(sel, root = document) {
  return root.querySelector(sel);
}

function el(tag, className, text) {
  const e = document.createElement(tag);
  if (className) e.className = className;
  if (text !== undefined) e.textContent = text;
  return e;
}

function formatUpdatedAt(iso) {
  const d = new Date(iso);
  const diffMin = Math.round((Date.now() - d.getTime()) / 60000);
  if (diffMin < 1) return "Updated just now";
  if (diffMin < 60) return `Updated ${diffMin}m ago`;
  const diffHr = Math.round(diffMin / 60);
  if (diffHr < 24) return `Updated ${diffHr}h ago`;
  const diffDay = Math.round(diffHr / 24);
  return `Updated ${diffDay}d ago`;
}

function localTime(fixture) {
  if (fixture.time_tbc) return "TBC";
  const d = new Date(fixture.kickoff_utc);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function monthKey(fixture) {
  const d = new Date(fixture.kickoff_utc);
  return `${d.getFullYear()}-${d.getMonth()}`;
}

function monthLabel(fixture) {
  const d = new Date(fixture.kickoff_utc);
  return d.toLocaleDateString([], { month: "long", year: "numeric" });
}

function isPast(fixture) {
  return new Date(fixture.kickoff_utc).getTime() < Date.now();
}

function isCancelledOrPostponed(fixture) {
  return fixture.status === "Postponed" || fixture.status === "Cancelled";
}

function findNextFixture(fixtures) {
  const now = Date.now();
  return fixtures.find(
    (f) => new Date(f.kickoff_utc).getTime() >= now && !isCancelledOrPostponed(f)
  );
}

function countdownText(fixture) {
  const diffMs = new Date(fixture.kickoff_utc).getTime() - Date.now();
  if (diffMs <= 0) return "Kicking off now";
  const days = Math.floor(diffMs / 86400000);
  const hours = Math.floor((diffMs % 86400000) / 3600000);
  if (days > 0) return `In ${days}d ${hours}h`;
  const mins = Math.floor((diffMs % 3600000) / 60000);
  return `In ${hours}h ${mins}m`;
}

function buildStatusChip(fixture) {
  if (fixture.status === "Postponed") return chip("Postponed", "postponed");
  if (fixture.status === "Cancelled") return chip("Cancelled", "cancelled");
  return null;
}

function chip(text, extraClass) {
  return el("span", `chip ${extraClass || ""}`.trim(), text);
}

function buildChannelChips(fixture) {
  const row = el("div", "chip-row");
  const statusChip = buildStatusChip(fixture);
  if (statusChip) {
    row.appendChild(statusChip);
    return row;
  }
  if (fixture.channels && fixture.channels.length) {
    for (const ch of fixture.channels) {
      row.appendChild(chip(ch, "channel"));
    }
  } else if (!isPast(fixture)) {
    row.appendChild(chip("Not televised / TBC", "tbc"));
  }
  return row;
}

function matchupText(fixture) {
  return fixture.is_home ? `Rangers vs ${fixture.opponent}` : `${fixture.opponent} vs Rangers`;
}

function buildFixtureCard(fixture) {
  const card = el("div", "fixture-card" + (isPast(fixture) ? " past" : ""));

  const d = new Date(fixture.kickoff_utc);
  const dateCol = el("div", "fixture-date-col");
  dateCol.appendChild(el("span", "day", String(d.getDate())));
  dateCol.appendChild(el("span", "dow", d.toLocaleDateString([], { weekday: "short" })));
  card.appendChild(dateCol);

  const main = el("div", "fixture-main");
  main.appendChild(el("div", "matchup", matchupText(fixture)));
  const sub = el("div", "sub");
  sub.appendChild(el("span", null, fixture.competition));
  if (fixture.stage) sub.appendChild(el("span", null, `· ${fixture.stage}`));
  main.appendChild(sub);
  card.appendChild(main);

  const right = el("div", "fixture-right");
  if (fixture.score && isPast(fixture)) {
    right.appendChild(el("span", "score", fixture.score));
  } else {
    right.appendChild(el("span", "kickoff-time", localTime(fixture)));
  }
  right.appendChild(buildChannelChips(fixture));
  card.appendChild(right);

  return card;
}

function buildHero(fixture) {
  const hero = el("div", "next-game");
  hero.appendChild(el("p", "label", "Next Game"));
  hero.appendChild(el("p", "matchup", matchupText(fixture)));

  const meta = el("div", "meta");
  const d = new Date(fixture.kickoff_utc);
  meta.appendChild(
    el("span", null, d.toLocaleDateString([], { weekday: "long", day: "numeric", month: "long" }))
  );
  meta.appendChild(el("span", null, "·"));
  meta.appendChild(el("span", null, localTime(fixture)));
  meta.appendChild(el("span", null, `· ${fixture.competition}`));
  hero.appendChild(meta);

  hero.appendChild(buildChannelChips(fixture));
  hero.appendChild(el("p", "countdown", countdownText(fixture)));

  return hero;
}

function render(data) {
  const app = $("#app");
  app.textContent = "";

  $("#updated-at").textContent = formatUpdatedAt(data.generated_at);

  if (!data.fixtures || data.fixtures.length === 0) {
    app.appendChild(el("p", "empty", "No fixtures available."));
    return;
  }

  const fixtures = [...data.fixtures].sort(
    (a, b) => new Date(a.kickoff_utc) - new Date(b.kickoff_utc)
  );

  const next = findNextFixture(fixtures);
  if (next) app.appendChild(buildHero(next));

  const fragment = document.createDocumentFragment();
  let currentMonth = null;
  let list = null;

  for (const fixture of fixtures) {
    const key = monthKey(fixture);
    if (key !== currentMonth) {
      currentMonth = key;
      const section = el("section", "month-section");
      section.appendChild(el("h2", "month-heading", monthLabel(fixture)));
      list = el("div", "fixture-list");
      section.appendChild(list);
      fragment.appendChild(section);
    }
    list.appendChild(buildFixtureCard(fixture));
  }

  app.appendChild(fragment);
}

async function main() {
  try {
    const res = await fetch(DATA_URL, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    render(data);
  } catch (err) {
    const app = $("#app");
    app.textContent = "";
    app.appendChild(
      el("p", "error", "Couldn't load fixtures. Check your connection and try again.")
    );
    console.error("Failed to load fixtures:", err);
  }

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("sw.js").catch((e) => console.error("SW register failed:", e));
  }
}

main();

// Periodically re-fetch and re-render so "updated X ago", the countdown,
// and past/future styling stay correct if the app is left open. It's a
// tiny JSON file, so a plain refetch every minute is cheap and simple.
setInterval(main, 60000);
