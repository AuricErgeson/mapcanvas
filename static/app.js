const $ = id => document.getElementById(id);

const PLACE_POOL = [
  "Venice, Italy",
  "Amsterdam, Netherlands",
  "Manhattan, New York",
  "Tokyo, Japan",
  "Paris, France",
  "Marrakesh, Morocco",
  "Suzhou, China",
  "Hamburg, Germany",
  "Copenhagen, Denmark",
  "Bruges, Belgium",
  "Stockholm, Sweden",
  "Lisbon, Portugal",
  "Fez, Morocco",
  "Prague, Czechia",
];

const LOADING_MSGS = [
  "Loading map data…",
  "Preparing geometry…",
  "Rendering poster…",
];

let PRESETS = {};
let preset = "gallery";
let circle = true;
let blobUrl = null;
let msgTimer = null;
let renderInFlight = false;
let initInFlight = false;
let ready = false;
let lastRender = null;
let changedDuringRender = false;

const fmtRadius = metres => metres >= 1000
  ? (metres / 1000).toString().replace(/\.0$/, "") + " km"
  : metres + " m";
const first = value => Array.isArray(value) ? value[0] : value;

function setStatus(message, state = "") {
  const status = $("status");
  status.textContent = message;
  status.dataset.state = state;
}

function setRangeFill(input) {
  const progress = ((+input.value - +input.min) / (+input.max - +input.min)) * 100;
  input.style.setProperty("--fill", progress + "%");
}

function markDirty() {
  if (renderInFlight) {
    changedDuringRender = true;
    return;
  }
  if (!lastRender) return;
  setStatus("Settings changed — preview not updated.");
}

function setSwatches(style) {
  document.querySelectorAll('input[type="color"]').forEach(input => {
    if (style[input.dataset.key]) input.value = first(style[input.dataset.key]);
  });
}

function currentStyle() {
  const style = {};
  document.querySelectorAll('input[type="color"]').forEach(input => {
    style[input.dataset.key] = input.value;
  });
  return style;
}

function toast(message) {
  const notice = $("toast");
  notice.textContent = message;
  notice.hidden = false;
  notice.classList.add("on");
}

function clearToast() {
  const notice = $("toast");
  notice.classList.remove("on");
  notice.hidden = true;
  notice.textContent = "";
}

function showError(message) {
  setStatus("Poster could not be rendered.", "error");
  if ($("map").hidden) {
    clearToast();
    $("placeholder").hidden = true;
    $("stageErrorMessage").textContent = message;
    $("stageError").setAttribute("role", "alert");
    $("stageError").hidden = false;
  } else {
    $("stageError").removeAttribute("role");
    toast(message);
  }
}

function busy(on) {
  $("overlay").classList.toggle("on", on);
  $("overlay").setAttribute("aria-hidden", String(!on));
  $("preview").setAttribute("aria-busy", String(on));
  $("generate").disabled = on || !ready;
  $("surprise").disabled = on || !ready;
  $("retry").disabled = on;
  $("save").disabled = on || !lastRender;
  $("generate").textContent = on
    ? "Rendering…"
    : ready
      ? "Render poster"
      : "Styles unavailable";
  clearInterval(msgTimer);
  if (on) {
    clearToast();
    let index = 0;
    $("overlayMsg").textContent = LOADING_MSGS[index];
    setStatus("Rendering poster…");
    msgTimer = setInterval(() => {
      index = (index + 1) % LOADING_MSGS.length;
      $("overlayMsg").textContent = LOADING_MSGS[index];
    }, 3500);
  }
}

async function displayPoster(blob) {
  const nextUrl = URL.createObjectURL(blob);
  const probe = new Image();
  try {
    await new Promise((resolve, reject) => {
      probe.onload = resolve;
      probe.onerror = () => reject(new Error("The generated poster could not be displayed."));
      probe.src = nextUrl;
    });
    if (probe.decode) await probe.decode();
  } catch (error) {
    URL.revokeObjectURL(nextUrl);
    throw error;
  }

  const previousUrl = blobUrl;
  blobUrl = nextUrl;
  const image = $("map");
  image.src = nextUrl;
  image.hidden = false;
  $("placeholder").hidden = true;
  $("stageError").hidden = true;
  $("stageError").removeAttribute("role");
  if (previousUrl) URL.revokeObjectURL(previousUrl);
}

async function generate() {
  if (renderInFlight || !ready) return;
  renderInFlight = true;
  changedDuringRender = false;
  busy(true);
  const startedAt = performance.now();
  const renderSnapshot = {
    place: $("place").value.trim() || "Berlin, Germany",
    dist: +$("radius").value,
    preset,
    style: currentStyle(),
    size: +$("size").value,
    circle,
    width_scale: +$("roadw").value,
  };

  try {
    const response = await fetch("/api/render", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(renderSnapshot),
    });
    if (!response.ok) {
      let message = "Render failed.";
      try { message = (await response.json()).error || message; } catch {}
      throw new Error(message);
    }

    await displayPoster(await response.blob());
    lastRender = renderSnapshot;
    $("save").disabled = false;
    $("map").alt = "Generated map poster for " + renderSnapshot.place;
    $("stageLabel").textContent = renderSnapshot.place;
    $("stageSpec").textContent = renderSnapshot.preset + " · " + renderSnapshot.size + " px";
    const seconds = ((performance.now() - startedAt) / 1000).toFixed(1);
    if (changedDuringRender) {
      setStatus("Poster rendered; settings have changed since this preview.");
    } else {
      setStatus("Poster rendered in " + seconds + " s.", "success");
    }
  } catch (error) {
    showError(error instanceof Error ? error.message : "Something went wrong while rendering.");
  } finally {
    renderInFlight = false;
    busy(false);
  }
}

function selectShape(nextCircle) {
  circle = nextCircle;
  $("shapeCircle").setAttribute("aria-pressed", String(circle));
  $("shapeSquare").setAttribute("aria-pressed", String(!circle));
  markDirty();
}

async function init() {
  if (initInFlight) return;
  initInFlight = true;
  ready = false;
  clearToast();
  $("stageError").removeAttribute("role");
  if (!lastRender) {
    $("stageError").hidden = true;
    $("placeholder").hidden = false;
  }
  $("generate").disabled = true;
  $("surprise").disabled = true;
  $("retry").disabled = true;
  $("generate").textContent = "Loading styles…";
  setStatus("Loading style library…");
  try {
    const response = await fetch("/api/presets");
    if (!response.ok) throw new Error("Style library could not be loaded.");
    const data = await response.json();
    if (!data || typeof data !== "object" || Array.isArray(data)) {
      throw new Error("Style library returned invalid data.");
    }
    const entries = Object.entries(data);
    if (!entries.length) throw new Error("No poster styles are available.");
    PRESETS = data;
    if (!PRESETS[preset]) preset = entries[0][0];

    const box = $("presets");
    box.replaceChildren();
    entries.forEach(([name, style]) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "chip";
      button.setAttribute("aria-pressed", String(name === preset));

      const dots = document.createElement("span");
      dots.className = "palette-dots";
      dots.setAttribute("aria-hidden", "true");
      ["bg", "water", "road", "accent"].forEach(key => {
        const dot = document.createElement("i");
        dot.style.background = first(style[key]);
        dots.appendChild(dot);
      });

      button.appendChild(dots);
      button.appendChild(document.createTextNode(name));
      button.addEventListener("click", () => {
        preset = name;
        box.querySelectorAll(".chip").forEach(chip => {
          chip.setAttribute("aria-pressed", String(chip === button));
        });
        setSwatches(style);
        markDirty();
      });
      box.appendChild(button);
    });

    setSwatches(PRESETS[preset]);
    ready = true;
    $("generate").disabled = false;
    $("generate").textContent = "Render poster";
    $("surprise").disabled = false;
    if (!lastRender) {
      $("stageError").hidden = true;
      $("placeholder").hidden = false;
    }
    setStatus("Ready.");
  } catch (error) {
    ready = false;
    $("generate").disabled = true;
    $("surprise").disabled = true;
    showError(error instanceof Error ? error.message : "The controls could not be initialized.");
  } finally {
    initInFlight = false;
    $("retry").disabled = false;
  }

  [$("radius"), $("roadw")].forEach(setRangeFill);
  $("radius").setAttribute("aria-valuetext", fmtRadius(+$("radius").value));
  $("roadw").setAttribute("aria-valuetext", (+$("roadw").value).toFixed(1) + " times");
}

$("controlsForm").addEventListener("submit", event => {
  event.preventDefault();
  generate();
});

$("radius").addEventListener("input", event => {
  $("radiusVal").textContent = fmtRadius(+event.target.value);
  event.target.setAttribute("aria-valuetext", fmtRadius(+event.target.value));
  setRangeFill(event.target);
  markDirty();
});

$("roadw").addEventListener("input", event => {
  $("roadwVal").textContent = (+event.target.value).toFixed(1) + "×";
  event.target.setAttribute("aria-valuetext", (+event.target.value).toFixed(1) + " times");
  setRangeFill(event.target);
  markDirty();
});

$("surprise").addEventListener("click", () => {
  $("place").value = PLACE_POOL[Math.floor(Math.random() * PLACE_POOL.length)];
  generate();
});

$("shapeCircle").addEventListener("click", () => selectShape(true));
$("shapeSquare").addEventListener("click", () => selectShape(false));
$("focusPlace").addEventListener("click", () => $("place").focus());
$("retry").addEventListener("click", () => ready ? generate() : init());

$("save").addEventListener("click", () => {
  if (!blobUrl || !lastRender) return;
  const link = document.createElement("a");
  link.href = blobUrl;
  link.download = (lastRender.place.replace(/\W+/g, "-").toLowerCase() || "map") + "-mapcanvas.png";
  link.click();
});

$("place").addEventListener("input", markDirty);
$("size").addEventListener("change", markDirty);
document.querySelectorAll('input[type="color"]').forEach(input => {
  input.addEventListener("input", markDirty);
});

window.addEventListener("pagehide", () => {
  if (blobUrl) URL.revokeObjectURL(blobUrl);
});

if (window.matchMedia("(max-width: 700px)").matches) $("advanced").open = false;
init();
