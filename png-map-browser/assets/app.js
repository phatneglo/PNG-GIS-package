const DATA_ROOT_CANDIDATES = ["png-json-maps", "../png-json-maps"];
const ADDRESS_ROOT_CANDIDATES = ["png-json-address", "../png-json-address"];
const DEFAULT_CENTER = [-6.315, 143.955];
const DEFAULT_ZOOM = 6;
const HOME_LAYER_ID = "regions";

const layerDefinitions = [
  { id: "country", label: "Country", source: (index) => index.country?.geojson, level: "country" },
  { id: "regions", label: "Regions", source: (index) => index.maps?.regions?.geojson, level: "region" },
  { id: "provinces_all", label: "Provinces", source: (index) => index.maps?.provinces_all?.geojson, level: "province" },
  { id: "districts_all", label: "Districts", source: (index) => index.maps?.districts_all?.geojson, level: "district" },
  { id: "llgs_all", label: "LLGs", source: (index) => index.maps?.llgs_all?.geojson, level: "llg" },
  { id: "wards_all", label: "Wards", source: (index) => index.maps?.wards_all?.geojson, level: "ward" },
];

const colors = {
  country: { stroke: "#b45309", fill: "#fbbf24" },
  region: { stroke: "#0f766e", fill: "#5eead4" },
  province: { stroke: "#1d4ed8", fill: "#93c5fd" },
  district: { stroke: "#7c2d12", fill: "#fdba74" },
  llg: { stroke: "#7c3aed", fill: "#c4b5fd" },
  ward: { stroke: "#be123c", fill: "#fda4af" },
};

const els = {
  yearSelect: document.querySelector("#yearSelect"),
  mapSelect: document.querySelector("#mapSelect"),
  baseLayerSelect: document.querySelector("#baseLayerSelect"),
  backButton: document.querySelector("#backButton"),
  fitButton: document.querySelector("#fitButton"),
  resetButton: document.querySelector("#resetButton"),
  currentTitle: document.querySelector("#currentTitle"),
  currentDetail: document.querySelector("#currentDetail"),
  featureSearch: document.querySelector("#featureSearch"),
  featureList: document.querySelector("#featureList"),
  addressSearch: document.querySelector("#addressSearch"),
  addressResults: document.querySelector("#addressResults"),
  breadcrumbs: document.querySelector("#breadcrumbs"),
  statusText: document.querySelector("#statusText"),
  sidebar: document.querySelector(".sidebar"),
  showSidebar: document.querySelector("#showSidebar"),
  collapseSidebar: document.querySelector("#collapseSidebar"),
  toast: document.querySelector("#appToast"),
  toastBody: document.querySelector("#toastBody"),
};

const state = {
  catalog: null,
  year: null,
  index: null,
  metadata: null,
  dataRoot: null,
  baseUrl: "",
  layer: null,
  geoLayer: null,
  baseLayer: null,
  features: [],
  addressRecords: [],
  addressByLlg: new Map(),
  path: [],
  availableLayerIds: [],
};

const map = L.map("map", { zoomControl: false }).setView(DEFAULT_CENTER, DEFAULT_ZOOM);
L.control.zoom({ position: "topright" }).addTo(map);

const baseLayers = {
  osm: {
    className: "",
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    layer: () => L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      crossOrigin: true,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }),
  },
  carto: {
    className: "",
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>, &copy; <a href="https://carto.com/attributions">CARTO</a>',
    layer: () => L.tileLayer("https://basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
      maxZoom: 20,
      crossOrigin: true,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>, &copy; <a href="https://carto.com/attributions">CARTO</a>',
    }),
  },
  none: {
    className: "plain-basemap",
    attribution: "",
    layer: () => L.layerGroup(),
  },
};

setBaseLayer("osm");

const legend = L.control({ position: "bottomright" });
legend.onAdd = () => {
  const div = L.DomUtil.create("div", "legend");
  div.innerHTML = '<strong>Click an area</strong><br>Drill down to the next PNG admin level.';
  return div;
};
legend.addTo(map);

async function init() {
  bindEvents();
  setStatus("Loading catalog");
  state.catalog = await loadCatalog();
  populateYears();
  await loadYear(selectInitialYear());
}

function bindEvents() {
  els.yearSelect.addEventListener("change", () => loadYear(els.yearSelect.value));
  els.mapSelect.addEventListener("change", () => loadTopLevel(els.mapSelect.value));
  els.baseLayerSelect.addEventListener("change", () => setBaseLayer(els.baseLayerSelect.value));
  els.backButton.addEventListener("click", goBack);
  els.fitButton.addEventListener("click", fitCurrentLayer);
  els.resetButton.addEventListener("click", () => loadTopLevel(HOME_LAYER_ID));
  els.featureSearch.addEventListener("input", renderFeatureList);
  els.addressSearch.addEventListener("input", renderAddressResults);
  els.showSidebar.addEventListener("click", () => els.sidebar.classList.add("is-open"));
  els.collapseSidebar.addEventListener("click", () => els.sidebar.classList.remove("is-open"));
}

function setBaseLayer(layerId) {
  const next = baseLayers[layerId] || baseLayers.osm;
  if (state.baseLayer) {
    state.baseLayer.remove();
  }

  map.getContainer().classList.toggle("plain-basemap", layerId === "none");
  state.baseLayer = next.layer().addTo(map);
  state.baseLayer.on?.("tileerror", () => {
    setStatus("Base map tile issue");
  });
  els.baseLayerSelect.value = layerId;
}

async function loadCatalog() {
  try {
    const catalog = await fetchJson("catalog.json");
    if (Array.isArray(catalog.years) && catalog.years.length) {
      const workingCatalog = await normalizeCatalog(catalog);
      if (workingCatalog.years.length) {
        return workingCatalog;
      }
    }
  } catch {
    showToast("No catalog.json found yet. Probing common year folders.");
  }

  return probeCatalog();
}

async function normalizeCatalog(catalog) {
  const years = [];
  for (const entry of catalog.years) {
    const candidates = [
      entry,
      ...DATA_ROOT_CANDIDATES.map((root) => ({
        year: entry.year,
        index: `${root}/${entry.year}/index.json`,
        metadata: `${root}/${entry.year}/metadata.json`,
      })),
    ];

    for (const candidate of candidates) {
      try {
        await fetchJson(candidate.index);
        years.push(candidate);
        break;
      } catch {
        // Try the next known layout.
      }
    }
  }
  return { ...catalog, years };
}

async function probeCatalog() {
  const currentYear = new Date().getFullYear();
  const candidates = [];
  for (let year = currentYear + 3; year >= 2015; year -= 1) {
    candidates.push(year.toString());
  }

  const years = [];
  for (const root of DATA_ROOT_CANDIDATES) {
    for (const year of candidates) {
      try {
        await fetchJson(`${root}/${year}/index.json`);
        years.push({
          year,
          index: `${root}/${year}/index.json`,
          metadata: `${root}/${year}/metadata.json`,
        });
      } catch {
        // Missing years are expected during probing.
      }
    }
    if (years.length) break;
  }

  if (!years.length) {
    throw new Error("No png-json-maps year folders were found. Place png-json-maps beside this folder or inside png-map-browser.");
  }
  return { years };
}

function populateYears() {
  const years = [...state.catalog.years].sort((a, b) => Number(b.year) - Number(a.year));
  els.yearSelect.replaceChildren(...years.map((entry) => {
    const option = document.createElement("option");
    option.value = entry.year;
    option.textContent = entry.year;
    return option;
  }));
}

function selectInitialYear() {
  const params = new URLSearchParams(window.location.search);
  const requestedYear = params.get("year");
  const availableYears = state.catalog.years.map((entry) => entry.year);
  return availableYears.includes(requestedYear) ? requestedYear : availableYears[0];
}

async function loadYear(year) {
  setStatus(`Loading ${year}`);
  state.year = year;
  els.yearSelect.value = year;
  const yearEntry = state.catalog.years.find((entry) => entry.year === year);
  const indexUrl = yearEntry?.index || `${DATA_ROOT_CANDIDATES[0]}/${year}/index.json`;
  state.baseUrl = indexUrl.replace(/index\.json$/, "");
  state.index = await fetchJson(indexUrl);
  try {
    const metadataUrl = yearEntry?.metadata || `${state.baseUrl}metadata.json`;
    state.metadata = await fetchJson(metadataUrl);
  } catch {
    state.metadata = null;
  }
  await loadAddressIndex(year);
  await populateMapSelect();
  await loadTopLevel(HOME_LAYER_ID);
}

async function loadAddressIndex(year) {
  state.addressRecords = [];
  const catalogCandidates = getAddressCandidatesForYear(year);

  for (const url of catalogCandidates) {
    try {
      const data = await fetchJson(url);
      state.addressRecords = Array.isArray(data.records) ? data.records : [];
      buildAddressIndexes();
      renderAddressResults();
      return;
    } catch {
      // Try the next known layout.
    }
  }

  buildAddressIndexes();
  renderAddressResults();
}

function buildAddressIndexes() {
  state.addressByLlg = new Map();

  for (const record of state.addressRecords) {
    if (record.level !== "ward") {
      continue;
    }

    const inferredLlgCode = record.llg_code || findLlgForAddress(record)?.code;
    if (!inferredLlgCode) {
      continue;
    }

    const wards = state.addressByLlg.get(inferredLlgCode) || [];
    wards.push(record);
    state.addressByLlg.set(inferredLlgCode, wards);
  }

  for (const wards of state.addressByLlg.values()) {
    wards.sort((a, b) => {
      const wardA = Number(a.ward_number || Number.MAX_SAFE_INTEGER);
      const wardB = Number(b.ward_number || Number.MAX_SAFE_INTEGER);
      return wardA - wardB || String(a.name || "").localeCompare(String(b.name || ""));
    });
  }
}

function getAddressCandidatesForYear(year) {
  const candidates = [];
  const indexPath = state.baseUrl.replace(/\/$/, "");
  const addressPath = indexPath
    .replace(/png-json-maps\/?$/, "png-json-address")
    .replace(/png-json-maps\/(\d+)$/, "png-json-address/$1");

  if (addressPath.includes("png-json-address")) {
    candidates.push(`${addressPath}/address-flat.json`);
  }

  for (const root of ADDRESS_ROOT_CANDIDATES) {
    candidates.push(`${root}/${year}/address-flat.json`);
  }

  return [...new Set(candidates)];
}

async function populateMapSelect() {
  const available = [];

  for (const definition of layerDefinitions) {
    const relativePath = definition.source(state.index);
    if (!relativePath) {
      continue;
    }

    const hasFeatures = await geoJsonHasFeatures(resolveDataPath(relativePath));
    if (hasFeatures) {
      available.push(definition);
    }
  }

  state.availableLayerIds = available.map((definition) => definition.id);
  const options = available.map((definition) => {
    const option = document.createElement("option");
    option.value = definition.id;
    option.textContent = definition.label;
    return option;
  });
  els.mapSelect.replaceChildren(...options);
}

async function loadTopLevel(layerId) {
  const safeLayerId = state.availableLayerIds.includes(layerId) ? layerId : state.availableLayerIds[0];
  const definition = layerDefinitions.find((item) => item.id === safeLayerId) || layerDefinitions[0];
  els.mapSelect.value = definition.id;
  state.path = [{ label: definition.label, action: () => loadTopLevel(definition.id) }];
  await loadLayer({
    title: definition.label,
    detail: `${state.year} ${definition.label.toLowerCase()} layer`,
    level: definition.level,
    relativePath: definition.source(state.index),
  });
}

async function drillDown(feature) {
  const props = feature.properties || {};
  const level = getFeatureLevel(props);
  const next = getNextLayer(props, level);

  if (!next?.relativePath) {
    showToast(level === "llg" ? "LLG is the most detailed boundary level available. Ward address records are shown in the popup." : "No deeper boundary file is available for this area.");
    focusFeature(feature);
    return;
  }

  const hasNextFeatures = await geoJsonHasFeatures(resolveDataPath(next.relativePath));
  if (!hasNextFeatures) {
    showToast(level === "llg" ? "No ward boundaries are available. Ward address records are shown in the LLG popup." : "No deeper boundary features are available for this area.");
    focusFeature(feature);
    return;
  }

  state.path.push({ label: props.name || props.code || next.title, action: () => loadLayer(next) });
  await loadLayer(next);
}

function getNextLayer(props, level) {
  if (level === "region") {
    const item = state.index.regions?.find((region) => region.code === props.code || region.code === props.region_code);
    return {
      title: item?.name || props.name || "Region provinces",
      detail: "Provinces in selected region",
      level: "province",
      relativePath: item?.provinces_geojson,
    };
  }

  if (level === "province") {
    const code = props.province_code || props.code;
    const item = state.index.provinces?.find((province) => province.code === code);
    return {
      title: item?.name || props.name || "Province districts",
      detail: "Districts in selected province",
      level: "district",
      relativePath: item?.districts_geojson,
    };
  }

  if (level === "district") {
    const code = props.district_code || props.code;
    const item = state.index.districts?.find((district) => district.code === code);
    return {
      title: item?.name || props.name || "District LLGs",
      detail: "LLGs in selected district",
      level: "llg",
      relativePath: item?.llgs_geojson,
    };
  }

  if (level === "llg") {
    const code = props.llg_code || props.code;
    const item = state.index.llgs?.find((llg) => llg.code === code);
    return {
      title: item?.name || props.name || "LLG wards",
      detail: "Wards in selected LLG",
      level: "ward",
      relativePath: item?.wards_geojson,
    };
  }

  if (level === "country") {
    return {
      title: "Regions",
      detail: "PNG regions",
      level: "region",
      relativePath: state.index.maps?.regions?.geojson,
    };
  }

  return null;
}

async function loadLayer({ title, detail, level, relativePath }) {
  if (!relativePath) {
    showToast("This layer is not available in the selected year.");
    return;
  }

  setStatus("Loading map");
  const data = await fetchJson(resolveDataPath(relativePath));
  state.layer = { title, detail, level, relativePath };
  state.features = data.features || [];
  drawLayer(data, level);
  renderCurrent();
  renderFeatureList();
  renderBreadcrumbs();
  setStatus(`${state.features.length.toLocaleString()} features`);
}

function drawLayer(data, level) {
  if (state.geoLayer) {
    state.geoLayer.remove();
  }

  const palette = colors[level] || colors.region;
  state.geoLayer = L.geoJSON(data, {
    style: {
      color: palette.stroke,
      weight: level === "country" ? 2.4 : 1.4,
      opacity: .95,
      fillColor: palette.fill,
      fillOpacity: level === "llg" || level === "ward" ? .48 : .62,
    },
    onEachFeature: (feature, layer) => {
      const props = feature.properties || {};
      layer.bindTooltip(props.name || props.code || "Unnamed area", { sticky: true });
      layer.bindPopup(buildPopup(props));
      layer.on({
        click: () => drillDown(feature),
        mouseover: () => layer.setStyle({ weight: 3, fillOpacity: .62 }),
        mouseout: () => state.geoLayer.resetStyle(layer),
      });
    },
  }).addTo(map);

  state.geoLayer.bringToFront();
  map.invalidateSize();
  fitCurrentLayer();
}

function renderCurrent() {
  els.currentTitle.textContent = state.layer?.title || "No layer";
  const level = state.layer?.level;
  const detailParts = [state.layer?.detail].filter(Boolean);

  if (level === "llg") {
    const wardCount = state.features.reduce((total, feature) => total + getWardsForFeature(feature).length, 0);
    detailParts.push(`${state.features.length.toLocaleString()} LLG boundaries`);
    detailParts.push(`${wardCount.toLocaleString()} matched ward address records`);
  }

  els.currentDetail.textContent = detailParts.join(" | ");
  els.backButton.disabled = state.path.length <= 1;
}

function renderFeatureList() {
  const query = els.featureSearch.value.trim().toLowerCase();
  const features = state.features.filter((feature) => {
    return !query || getFeatureSearchText(feature).includes(query);
  });

  const fragment = document.createDocumentFragment();
  for (const feature of features.slice(0, 250)) {
    const props = feature.properties || {};
    const button = document.createElement("button");
    button.type = "button";
    button.className = "feature-item";
    const meta = getFeatureListMeta(feature);
    button.innerHTML = `
      <span>
        <span class="feature-name">${escapeHtml(props.name || "Unnamed area")}</span>
        <span class="feature-code">${escapeHtml(meta)}</span>
      </span>
      <i class="bi bi-chevron-right text-secondary"></i>
    `;
    button.addEventListener("click", () => drillDown(feature));
    fragment.append(button);
  }

  if (features.length > 250) {
    const more = document.createElement("div");
    more.className = "text-secondary small px-2 py-3";
    more.textContent = `Showing first 250 of ${features.length.toLocaleString()} matches. Use search to narrow results.`;
    fragment.append(more);
  }

  if (!features.length) {
    const empty = document.createElement("div");
    empty.className = "text-secondary small px-2 py-3";
    empty.textContent = "No matching features.";
    fragment.append(empty);
  }

  els.featureList.replaceChildren(fragment);
}

function renderAddressResults() {
  const query = els.addressSearch.value.trim().toLowerCase();
  const fragment = document.createDocumentFragment();

  if (!state.addressRecords.length) {
    const empty = document.createElement("div");
    empty.className = "text-secondary small px-2 py-2";
    empty.textContent = "Address index not found for this year.";
    fragment.append(empty);
    els.addressResults.replaceChildren(fragment);
    return;
  }

  if (query.length < 2) {
    const hint = document.createElement("div");
    hint.className = "text-secondary small px-2 py-2";
    hint.textContent = `${state.addressRecords.length.toLocaleString()} address records. Type at least 2 characters.`;
    fragment.append(hint);
    els.addressResults.replaceChildren(fragment);
    return;
  }

  const results = state.addressRecords
    .filter((record) => `${record.label || ""} ${record.code || ""}`.toLowerCase().includes(query))
    .slice(0, 20);

  for (const record of results) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "address-item";
    button.innerHTML = `
      <span class="address-level">${escapeHtml(record.level || "")}</span>
      <div class="address-label">${escapeHtml(record.label || record.name || "")}</div>
      <div class="address-code">${escapeHtml(record.code || "")} &middot; ${escapeHtml(record.code_system || "unknown code system")}</div>
    `;
    button.addEventListener("click", () => selectAddress(record));
    fragment.append(button);
  }

  if (!results.length) {
    const empty = document.createElement("div");
    empty.className = "text-secondary small px-2 py-2";
    empty.textContent = "No address matches.";
    fragment.append(empty);
  }

  els.addressResults.replaceChildren(fragment);
}

async function selectAddress(record) {
  const target = getAddressTarget(record);
  if (!target) {
    showToast("This address level is not available on the map.");
    return;
  }

  await loadTopLevel(target.layerId);
  const feature = state.features.find((item) => {
    const props = item.properties || {};
    return props.code === target.code || props[target.prop] === target.code;
  });

  if (feature) {
    focusFeature(feature);
    if (record.level === "ward" && !record.geometry_available) {
      showToast("Ward has no boundary geometry. Focused the best matching parent boundary.");
    }
  } else {
    showToast("Address found, but no matching boundary was found in this layer.");
  }
}

function getAddressTarget(record) {
  if (record.level === "region") {
    return { layerId: "regions", code: record.region_code || record.code, prop: "region_code" };
  }
  if (record.level === "province") {
    return { layerId: "provinces_all", code: record.province_code || record.code, prop: "province_code" };
  }
  if (record.level === "district") {
    return record.district_code
      ? { layerId: "districts_all", code: record.district_code || record.code, prop: "district_code" }
      : findAddressParentTarget(record, "district");
  }
  if (record.level === "llg") {
    return record.llg_code
      ? { layerId: "llgs_all", code: record.llg_code || record.code, prop: "llg_code" }
      : findAddressParentTarget(record, "llg");
  }
  if (record.level === "ward") {
    if (state.availableLayerIds.includes("wards_all") && record.ward_code) {
      return { layerId: "wards_all", code: record.ward_code || record.code, prop: "ward_code" };
    }
    if (record.llg_code) {
      return { layerId: "llgs_all", code: record.llg_code, prop: "llg_code" };
    }
    return findAddressParentTarget(record, "llg");
  }
  return null;
}

function findAddressParentTarget(record, preferredLevel) {
  if (preferredLevel === "llg") {
    const llg = findLlgForAddress(record);
    if (llg) {
      return { layerId: "llgs_all", code: llg.code, prop: "llg_code" };
    }
  }

  const district = findDistrictForAddress(record);
  if (district) {
    return { layerId: "districts_all", code: district.code, prop: "district_code" };
  }

  const province = findProvinceForAddress(record);
  if (province) {
    return { layerId: "provinces_all", code: province.code, prop: "province_code" };
  }

  return null;
}

function findLlgForAddress(record) {
  const province = findProvinceForAddress(record);
  const provinceLlgs = state.index.llgs?.filter((llg) => !province || llg.province_code === province.code) || [];
  const district = findDistrictForAddress(record);
  const districtLlgs = district ? provinceLlgs.filter((llg) => llg.district_code === district.code) : [];
  const sourceLlgName = normalizeAddressName(record.llg_name || record.source_llg_name);

  const exactLlg = provinceLlgs.find((llg) => normalizeAddressName(llg.name) === sourceLlgName);
  if (exactLlg) {
    return exactLlg;
  }

  if (districtLlgs.length === 1) {
    return districtLlgs[0];
  }

  if (provinceLlgs.length === 1) {
    return provinceLlgs[0];
  }

  return null;
}

function findDistrictForAddress(record) {
  const province = findProvinceForAddress(record);
  const sourceDistrictName = normalizeAddressName(record.district_name || record.source_district_name);
  const districts = state.index.districts?.filter((district) => !province || district.province_code === province.code) || [];
  const exactDistrict = districts.find((district) => normalizeAddressName(district.name) === sourceDistrictName);

  if (exactDistrict) {
    return exactDistrict;
  }

  if (districts.length === 1) {
    return districts[0];
  }

  return null;
}

function findProvinceForAddress(record) {
  if (record.province_code) {
    const byCode = state.index.provinces?.find((province) => province.code === record.province_code);
    if (byCode) {
      return byCode;
    }
  }

  const sourceProvinceName = normalizeAddressName(record.province_name || record.source_province_name);
  return state.index.provinces?.find((province) => normalizeAddressName(province.name) === sourceProvinceName) || null;
}

function normalizeAddressName(value) {
  return String(value || "")
    .toLowerCase()
    .replaceAll("&", "and")
    .replace(/\([^)]*\)/g, "")
    .replace(/\b(province|district|rural|urban|llg|local level government)\b/g, "")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

function renderBreadcrumbs() {
  const fragment = document.createDocumentFragment();
  state.path.forEach((crumb, index) => {
    if (index > 0) {
      const separator = document.createElement("span");
      separator.className = "crumb-separator";
      separator.textContent = "/";
      fragment.append(separator);
    }
    const button = document.createElement("button");
    button.type = "button";
    button.className = "crumb-button";
    button.textContent = crumb.label;
    button.addEventListener("click", async () => {
      state.path = state.path.slice(0, index + 1);
      await crumb.action();
    });
    fragment.append(button);
  });
  els.breadcrumbs.replaceChildren(fragment);
}

function goBack() {
  if (state.path.length <= 1) {
    return;
  }
  state.path.pop();
  const previous = state.path[state.path.length - 1];
  previous.action();
}

function fitCurrentLayer() {
  if (!state.geoLayer) {
    map.setView(DEFAULT_CENTER, DEFAULT_ZOOM);
    return;
  }
  const bounds = state.geoLayer.getBounds();
  if (bounds.isValid()) {
    map.fitBounds(bounds, { padding: [24, 24], maxZoom: 11 });
  }
}

function focusFeature(feature) {
  const layer = findLayerForFeature(feature);
  if (!layer) {
    return;
  }
  const bounds = layer.getBounds?.();
  if (bounds?.isValid()) {
    map.fitBounds(bounds, { padding: [32, 32], maxZoom: 12 });
    layer.openPopup();
  }
}

function findLayerForFeature(feature) {
  let found = null;
  const code = feature.properties?.code;
  state.geoLayer?.eachLayer((layer) => {
    if (layer.feature?.properties?.code === code) {
      found = layer;
    }
  });
  return found;
}

function getFeatureListMeta(feature) {
  const props = feature.properties || {};
  const parts = [props.code || props.parent_code].filter(Boolean);
  const wards = getWardsForFeature(feature);

  if (wards.length) {
    parts.push(`${wards.length.toLocaleString()} wards`);
  }

  return parts.join(" | ");
}

function getFeatureSearchText(feature) {
  const props = feature.properties || {};
  const wardText = getWardsForFeature(feature)
    .map((ward) => `${ward.name || ""} ${ward.code || ""} ${ward.ward_number || ""}`)
    .join(" ");
  return `${props.name || ""} ${props.code || ""} ${props.parent_code || ""} ${wardText}`.toLowerCase();
}

function getWardsForFeature(feature) {
  return getWardsForLlgCode(getLlgCodeFromProps(feature.properties || {}));
}

function getWardsForLlgCode(llgCode) {
  if (!llgCode) {
    return [];
  }
  return state.addressByLlg.get(llgCode) || [];
}

function getLlgCodeFromProps(props) {
  return props.llg_code || (getFeatureLevel(props) === "llg" ? props.code : "");
}

function getFeatureLevel(props) {
  const explicit = props.admin_level_name;
  if (explicit) {
    return explicit;
  }
  if (props.llg_code) return "llg";
  if (props.district_code) return "district";
  if (props.province_code) return "province";
  if (props.region_code) return "region";
  return "country";
}

function buildPopup(props) {
  const level = getFeatureLevel(props);
  const wards = level === "llg" ? getWardsForLlgCode(getLlgCodeFromProps(props)) : [];
  const rows = [
    ["Code", props.code],
    ["Name", props.name],
    ["Region", props.region_name],
    ["Province", props.province_name],
    ["District", props.district_name],
    ["LLG", props.llg_name],
  ].filter(([, value]) => value);

  return `
    <div class="popup-title">${escapeHtml(props.name || props.code || "Area")}</div>
    <table class="popup-table">${rows.map(([key, value]) => (
      `<tr><td class="text-secondary">${escapeHtml(key)}</td><td>${escapeHtml(value)}</td></tr>`
    )).join("")}</table>
    ${level === "llg" ? buildWardSummary(wards) : ""}
    <div class="small text-secondary mt-2">${escapeHtml(level === "llg" ? "LLG is the deepest mapped boundary. Use Address finder for wards." : "Click the shape to browse deeper.")}</div>
  `;
}

function buildWardSummary(wards) {
  if (!wards.length) {
    return `
      <div class="popup-wards">
        <div class="popup-section-title">Wards</div>
        <div class="small text-secondary">No ward address records matched this LLG.</div>
      </div>
    `;
  }

  const visibleWards = wards.slice(0, 80);
  const hiddenCount = wards.length - visibleWards.length;

  return `
    <div class="popup-wards">
      <div class="popup-section-title">Wards (${wards.length.toLocaleString()})</div>
      <div class="ward-list">
        ${visibleWards.map((ward) => `
          <div class="ward-row">
            <div>
              <div class="ward-name">${escapeHtml(formatWardName(ward))}</div>
              <div class="ward-code">${escapeHtml(ward.code || "")}</div>
            </div>
            ${ward.matched_to_map === false ? '<span class="ward-badge">unmatched</span>' : ""}
          </div>
        `).join("")}
      </div>
      ${hiddenCount > 0 ? `<div class="small text-secondary mt-1">${hiddenCount.toLocaleString()} more wards. Use Address finder to search within this LLG.</div>` : ""}
    </div>
  `;
}

function formatWardName(ward) {
  const number = ward.ward_number ? `${ward.ward_number}. ` : "";
  return `${number}${ward.name || "Unnamed ward"}`;
}

function resolveDataPath(relativePath) {
  return `${state.baseUrl}${relativePath}`;
}

async function fetchJson(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load ${url}: ${response.status}`);
  }
  return response.json();
}

async function geoJsonHasFeatures(url) {
  try {
    const data = await fetchJson(url);
    return Array.isArray(data.features) && data.features.length > 0;
  } catch {
    return false;
  }
}

function setStatus(text) {
  els.statusText.textContent = text;
}

function showToast(message) {
  els.toastBody.textContent = message;
  bootstrap.Toast.getOrCreateInstance(els.toast).show();
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

init().catch((error) => {
  console.error(error);
  setStatus("Load failed");
  showToast(error.message);
});
