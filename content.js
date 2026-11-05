"use strict";

const RECENT_DAYS = 7;
const CACHE_KEY = "alma-sync-helper:recent";
const CACHE_MINUTES = 10;
const PARALLEL_FETCHES = 3;
const DAY_MS = 24 * 60 * 60 * 1000;

function startOfDay(date) {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

function daysUntil(timestampSeconds) {
  const due = startOfDay(new Date(timestampSeconds * 1000));
  return Math.round((due - startOfDay(new Date())) / DAY_MS);
}

function badgeFor(days) {
  if (days < 0) return { text: "Overdue", level: "urgent" };
  if (days === 0) return { text: "Today", level: "urgent" };
  if (days === 1) return { text: "Tomorrow", level: "soon" };
  return { text: `${days} days`, level: days <= 3 ? "near" : "later" };
}

function addDaysLeftBadges(table) {
  for (const row of table.querySelectorAll("tbody tr")) {
    const cell = row.querySelector("td[data-sortable-val]");
    const timestamp = Number(cell?.dataset.sortableVal);
    if (!timestamp || cell.querySelector(".ash-badge")) continue;
    const { text, level } = badgeFor(daysUntil(timestamp));
    const badge = document.createElement("span");
    badge.className = `ash-badge ash-${level}`;
    badge.textContent = text;
    cell.appendChild(badge);
  }
}

async function fetchPage(path) {
  const response = await fetch(path, { credentials: "same-origin" });
  if (!response.ok) throw new Error(`${path} returned ${response.status}`);
  return new DOMParser().parseFromString(await response.text(), "text/html");
}

async function getClasses() {
  const page = await fetchPage("/home/schedule");
  const classes = new Map();
  for (const link of page.querySelectorAll("a[href*='/home/class/']")) {
    const path = link.getAttribute("href").split("?")[0];
    const name = link.textContent.trim();
    if (name && !classes.has(path)) classes.set(path, name);
  }
  return [...classes].map(([path, name]) => ({ path, name }));
}

function parseGradedRows(page, className) {
  const cutoff = Date.now() / 1000 - RECENT_DAYS * 24 * 60 * 60;
  const graded = [];
  for (const row of page.querySelectorAll("table tbody tr")) {
    const link = row.querySelector("td.name a[href^='/home/assignment/']");
    const updated = Number(row.querySelector("td.updated")?.dataset.sortableVal);
    const gradeCell = row.querySelector("td.grade");
    const letter = gradeCell?.firstChild?.textContent.trim();
    if (!link || !updated || updated < cutoff || !/^[A-F][+-]?$/.test(letter || "")) continue;
    graded.push({
      className,
      name: link.textContent.trim() || "Untitled assignment",
      href: link.getAttribute("href"),
      letter,
      percent: Number(gradeCell.dataset.sortableVal),
      points: row.querySelector("td.points")?.textContent.trim() || "",
      updated,
    });
  }
  return graded;
}

async function fetchRecentGrades() {
  const classes = await getClasses();
  const results = [];
  let next = 0;
  async function worker() {
    while (next < classes.length) {
      const { path, name } = classes[next++];
      results.push(...parseGradedRows(await fetchPage(path), name));
    }
  }
  await Promise.all(Array.from({ length: PARALLEL_FETCHES }, worker));
  return results.sort((a, b) => b.updated - a.updated);
}

function readCache() {
  try {
    const cached = JSON.parse(sessionStorage.getItem(CACHE_KEY));
    return cached && Date.now() - cached.savedAt < CACHE_MINUTES * 60 * 1000 ? cached.grades : null;
  } catch {
    return null;
  }
}

function writeCache(grades) {
  try {
    sessionStorage.setItem(CACHE_KEY, JSON.stringify({ savedAt: Date.now(), grades }));
  } catch {
    // Storage can be unavailable; the box still works without the cache.
  }
}

function scoreLevel(percent) {
  if (percent < 70) return "low";
  return percent >= 90 ? "high" : "mid";
}

function gradeRow(grade) {
  const row = document.createElement("li");
  row.className = "ash-grade";

  const score = document.createElement("span");
  score.className = `ash-score ash-${scoreLevel(grade.percent)}`;
  score.textContent = `${grade.letter} ${grade.percent}%`;

  const details = document.createElement("span");
  details.className = "ash-details";
  const link = document.createElement("a");
  link.href = grade.href;
  link.textContent = grade.name;
  const meta = document.createElement("small");
  const date = new Date(grade.updated * 1000).toLocaleDateString(undefined, { month: "short", day: "numeric" });
  meta.textContent = `${grade.className} · ${grade.points} · ${date}`;
  details.append(link, meta);

  row.append(score, details);
  return row;
}

function showGrades(box, grades) {
  const body = box.querySelector(".ash-body");
  body.textContent = "";
  if (grades.length === 0) {
    body.textContent = `No new grades in the last ${RECENT_DAYS} days.`;
    return;
  }
  const list = document.createElement("ul");
  list.append(...grades.map(gradeRow));
  body.appendChild(list);
}

function addRecentGradesBox(table) {
  const box = document.createElement("details");
  box.className = "ash-box";
  box.open = true;
  const title = document.createElement("summary");
  title.textContent = `Recently graded (last ${RECENT_DAYS} days)`;
  const body = document.createElement("div");
  body.className = "ash-body";
  body.textContent = "Loading grades...";
  box.append(title, body);
  table.parentElement.insertBefore(box, table);
  return box;
}

async function loadRecentGrades(box) {
  const cached = readCache();
  if (cached) {
    showGrades(box, cached);
    return;
  }
  try {
    const grades = await fetchRecentGrades();
    writeCache(grades);
    showGrades(box, grades);
  } catch (error) {
    console.warn("Alma Sync Helper:", error);
    box.querySelector(".ash-body").textContent = "Couldn't load recent grades. Refresh the page to try again.";
  }
}

const table = document.querySelector("table.upcoming-assignments");
if (table) {
  addDaysLeftBadges(table);
  loadRecentGrades(addRecentGradesBox(table));
}
