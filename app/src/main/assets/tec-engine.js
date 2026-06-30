/**
 * TEC Engine - Offline TEC prediction using CatBoost tree inference.
 *
 * Pipeline: Feature Construction -> Tree Inference -> EOF Reconstruction -> GeoJSON
 *
 * Data files required (loaded at init):
 *   - tec_trees.json  (31 MB) - CatBoost oblivious tree structure
 *   - eof_maps.json   (874 KB) - EOF basis functions (71x73x15)
 *   - tec_mean.json   (49 KB)  - TEC climatological mean (71x73)
 */

(function (root) {
  "use strict";

  // ========================================================
  // Constants
  // ========================================================

  var N_LAT = 71;
  var N_LON = 73;
  var N_MODES = 15;
  var N_FEATURES = 32;

  var SHORT_LAGS = [1, 3, 6, 12, 24];
  var SOLAR_LAGS = [24, 72, 168, 648];

  var LATS = [];
  var LONS = [];
  for (var i = 0; i < N_LAT; i++) LATS.push(-87.5 + i * 2.5);
  for (var j = 0; j < N_LON; j++) LONS.push(-180 + j * 5);

  // ========================================================
  // TecEngine Class
  // ========================================================

  function TecEngine() {
    this.trees = null;       // { depth, n_targets, bias, trees[] }
    this.eofMaps = null;     // Float64Array[71*73*15]
    this.tecMean = null;     // Float64Array[71*73]
    this.ready = false;
  }

  /**
   * Initialize the engine by loading all data files.
   * @param {string} basePath - Base path for data files (default: same directory as HTML)
   * @returns {Promise<void>}
   */
  TecEngine.prototype.init = function (basePath) {
    var self = this;
    basePath = basePath || "";

    return Promise.all([
      fetchJSON(basePath + "tec_trees.json"),
      fetchJSON(basePath + "eof_maps.json"),
      fetchJSON(basePath + "tec_mean.json"),
    ]).then(function (results) {
      self.trees = results[0];
      self.eofMaps = flattenNestedArray(results[1].data);
      self.tecMean = flattenNestedArray(results[2].data);
      self.ready = true;
    });
  };

  /**
   * Get engine status.
   * @returns {{ ready: boolean, nTrees: number, depth: number, nTargets: number }}
   */
  TecEngine.prototype.getStatus = function () {
    return {
      ready: this.ready,
      nTrees: this.trees ? this.trees.trees.length : 0,
      depth: this.trees ? this.trees.depth : 0,
      nTargets: this.trees ? this.trees.n_targets : 0,
    };
  };

  /**
   * Build the 32-dimensional feature vector.
   * @param {Object} params - { year, doy, ut_hour, drivers, memory_lags, solar_lags }
   * @returns {Float64Array} - 32 features
   */
  TecEngine.prototype.buildFeatureVector = function (params) {
    var features = new Float64Array(N_FEATURES);
    var drivers = params.drivers || {};
    var memoryLags = params.memory_lags || {};
    var solarLags = params.solar_lags || {};
    var doy = params.doy || 1;
    var utHour = params.ut_hour || 0;

    // [0-3] Time encoding
    features[0] = Math.sin(2 * Math.PI * doy / 366);
    features[1] = Math.cos(2 * Math.PI * doy / 366);
    features[2] = Math.sin(2 * Math.PI * utHour / 24);
    features[3] = Math.cos(2 * Math.PI * utHour / 24);

    // [4-8] Current solar/geomagnetic drivers
    features[4] = drivers.f107 || 0;
    features[5] = drivers.f107a || 0;
    features[6] = drivers.dst || 0;
    features[7] = drivers.ap || 0;
    features[8] = drivers.kp || 0;

    // [9-23] Geomagnetic lag features (5 lags x 3 vars)
    var idx = 9;
    for (var i = 0; i < SHORT_LAGS.length; i++) {
      var lag = SHORT_LAGS[i];
      features[idx++] = getLagValue(memoryLags, "dst", lag, drivers.dst || 0);
      features[idx++] = getLagValue(memoryLags, "ap", lag, drivers.ap || 0);
      features[idx++] = getLagValue(memoryLags, "kp", lag, drivers.kp || 0);
    }

    // [24-31] Solar lag features (4 lags x 2 vars)
    for (var i = 0; i < SOLAR_LAGS.length; i++) {
      var lag = SOLAR_LAGS[i];
      features[idx++] = getLagValue(solarLags, "f107", lag, drivers.f107 || 0);
      features[idx++] = getLagValue(solarLags, "f107a", lag, drivers.f107a || 0);
    }

    return features;
  };

  /**
   * Run CatBoost tree inference to get principal component coefficients.
   * @param {Float64Array} features - 32-dimensional feature vector
   * @returns {Float64Array} - 15 PC coefficients
   */
  TecEngine.prototype.predictPC = function (features) {
    var treeData = this.trees;
    var depth = treeData.depth;
    var nTargets = treeData.n_targets;
    var bias = treeData.bias;
    var allTrees = treeData.trees;

    var result = new Float64Array(nTargets);
    for (var t = 0; t < nTargets; t++) result[t] = bias[t];

    for (var treeIdx = 0; treeIdx < allTrees.length; treeIdx++) {
      var tree = allTrees[treeIdx];
      var feat = tree.f;
      var bord = tree.b;
      var vals = tree.v;

      // Traverse oblivious tree
      var leafIdx = 0;
      for (var level = 0; level < depth; level++) {
        if (features[feat[level]] > bord[level]) {
          leafIdx = leafIdx * 2 + 1;
        } else {
          leafIdx = leafIdx * 2 + 0;
        }
      }

      // Reverse bits (CatBoost oblivious tree leaf indexing)
      leafIdx = reverseBits(leafIdx, depth);

      // Add leaf values for all targets
      var base = leafIdx * nTargets;
      for (var t = 0; t < nTargets; t++) {
        result[t] += vals[base + t];
      }
    }

    return result;
  };

  /**
   * Reconstruct TEC map from PC coefficients.
   * @param {Float64Array} pcCoeffs - 15 PC coefficients
   * @returns {Float64Array} - 71x73 TEC grid (row-major)
   */
  TecEngine.prototype.reconstructTEC = function (pcCoeffs) {
    var tec = new Float64Array(N_LAT * N_LON);
    for (var i = 0; i < N_LAT; i++) {
      for (var j = 0; j < N_LON; j++) {
        var sum = 0;
        for (var k = 0; k < N_MODES; k++) {
          sum += this.eofMaps[i * N_LON * N_MODES + j * N_MODES + k] * pcCoeffs[k];
        }
        tec[i * N_LON + j] = this.tecMean[i * N_LON + j] + sum;
      }
    }
    return tec;
  };

  /**
   * End-to-end TEC prediction: features -> tree inference -> EOF reconstruction -> GeoJSON.
   * @param {Object} params - { year, doy, ut_hour, drivers, memory_lags, solar_lags }
   * @returns {Promise<Object>} - GeoJSON FeatureCollection
   */
  TecEngine.prototype.predict = function (params) {
    var self = this;
    return new Promise(function (resolve) {
      var features = self.buildFeatureVector(params);
      var pcCoeffs = self.predictPC(features);
      var tecMap = self.reconstructTEC(pcCoeffs);
      var geojson = tecToGeoJSON(tecMap, params.year, params.doy, params.ut_hour);
      resolve(geojson);
    });
  };

  /**
   * Get TEC value at a specific lat/lon by bilinear interpolation.
   * @param {Float64Array} tecMap - 71x73 TEC grid
   * @param {number} lat - Latitude (-90 to 90)
   * @param {number} lon - Longitude (-180 to 180)
   * @returns {number} - Interpolated TEC value
   */
  TecEngine.prototype.interpolateTEC = function (tecMap, lat, lon) {
    // Find grid indices
    var latIdx = (lat + 87.5) / 2.5;
    var lonIdx = (lon + 180) / 5;

    var i0 = Math.floor(latIdx);
    var j0 = Math.floor(lonIdx);
    var i1 = Math.min(i0 + 1, N_LAT - 1);
    var j1 = Math.min(j0 + 1, N_LON - 1);
    i0 = Math.max(0, i0);
    j0 = Math.max(0, j0);

    var fi = latIdx - i0;
    var fj = lonIdx - j0;

    var v00 = tecMap[i0 * N_LON + j0];
    var v01 = tecMap[i0 * N_LON + j1];
    var v10 = tecMap[i1 * N_LON + j0];
    var v11 = tecMap[i1 * N_LON + j1];

    return v00 * (1 - fi) * (1 - fj) +
           v10 * fi * (1 - fj) +
           v01 * (1 - fi) * fj +
           v11 * fi * fj;
  };

  // ========================================================
  // Helper Functions
  // ========================================================

  function getLagValue(lags, varName, lag, fallback) {
    if (!lags || !lags[varName]) return fallback;
    var val = lags[varName][lag];
    if (val === undefined) val = lags[varName][String(lag)];
    return val !== undefined ? val : fallback;
  }

  function reverseBits(n, depth) {
    var result = 0;
    for (var i = 0; i < depth; i++) {
      result = result * 2 + (n & 1);
      n = n >> 1;
    }
    return result;
  }

  function flattenNestedArray(arr) {
    // Flatten a nested JS array (from JSON) into a Float64Array
    var flat = [];
    function recurse(a) {
      for (var i = 0; i < a.length; i++) {
        if (Array.isArray(a[i])) {
          recurse(a[i]);
        } else {
          flat.push(a[i]);
        }
      }
    }
    recurse(arr);
    return new Float64Array(flat);
  }

  // AndroidBridge data cache (populated by preload)
  var bridgeCache = {};

  // AndroidBridge method map
  var BRIDGE_MAP = {
    "tec_trees.json": "getTecTreesData",
    "eof_maps.json": "getEofMapsData",
    "tec_mean.json": "getTecMeanData",
    "glotec_data.geojson": "getGlotecData",
  };

  // ========================================================
  // IndexedDB 缓存层：首次加载后缓存解析好的模型数据，
  // 后续页面切换无需重新 fetch 和 JSON.parse（约 31 MB）
  // ========================================================
  var DB_NAME = "TecEngineCache";
  var DB_VERSION = 2;
  var STORE_NAME = "parsedData";
  var CACHE_KEY_PREFIX = "tec_";
  var CACHE_VERSION = 2; // 模型文件更新时递增，使旧缓存失效

  function openDB() {
    return new Promise(function (resolve, reject) {
      var req = indexedDB.open(DB_NAME, DB_VERSION);
      req.onupgradeneeded = function (e) {
        var db = e.target.result;
        if (!db.objectStoreNames.contains(STORE_NAME)) {
          db.createObjectStore(STORE_NAME);
        }
      };
      req.onsuccess = function (e) { resolve(e.target.result); };
      req.onerror = function (e) { reject(e.target.error); };
    });
  }

  function getFromCache(filename) {
    var key = CACHE_KEY_PREFIX + filename;
    return openDB().then(function (db) {
      return new Promise(function (resolve, reject) {
        var tx = db.transaction(STORE_NAME, "readonly");
        var store = tx.objectStore(STORE_NAME);
        var req = store.get(key);
        req.onsuccess = function () {
          var entry = req.result;
          if (entry && entry._cacheVersion === CACHE_VERSION) {
            console.log("[TEC Engine] Cache HIT for " + filename);
            resolve(entry.data);
          } else {
            if (entry) console.log("[TEC Engine] Cache stale for " + filename + ", refetching");
            resolve(null);
          }
        };
        req.onerror = function () { resolve(null); };
      });
    }).catch(function () { return null; });
  }

  function putInCache(filename, data) {
    var key = CACHE_KEY_PREFIX + filename;
    return openDB().then(function (db) {
      return new Promise(function (resolve, reject) {
        var tx = db.transaction(STORE_NAME, "readwrite");
        var store = tx.objectStore(STORE_NAME);
        store.put({ data: data, _cacheVersion: CACHE_VERSION }, key);
        tx.oncomplete = function () {
          console.log("[TEC Engine] Cached " + filename + " in IndexedDB");
          resolve();
        };
        tx.onerror = function () { resolve(); }; // 缓存失败不影响主流程
      });
    }).catch(function () { /* ignore */ });
  }

  /**
   * Load JSON data with multiple fallback strategies:
   * 0. IndexedDB cache (fastest, persists across page loads)
   * 1. AndroidBridge - native preloaded data (fast, Android only)
   * 2. fetch() - works in browsers and modern WebViews
   * 3. XMLHttpRequest - fallback for file:// URLs
   */
  function fetchJSON(url) {
    var filename = url.split("/").pop();
    var bridgeMethod = BRIDGE_MAP[filename];

    // Strategy 0: IndexedDB cache
    return getFromCache(filename).then(function (cached) {
      if (cached) return cached;
      return fetchFromNetwork(url, filename, bridgeMethod);
    });
  }

  function fetchFromNetwork(url, filename, bridgeMethod) {
    // Strategy 1: AndroidBridge (if available, skip network requests)
    if (bridgeMethod && window.AndroidBridge && typeof AndroidBridge[bridgeMethod] === "function") {
      try {
        var raw = AndroidBridge[bridgeMethod]();
        if (raw) {
          console.log("[TEC Engine] Loaded " + filename + " via AndroidBridge");
          var data = JSON.parse(raw);
          putInCache(filename, data);
          return Promise.resolve(data);
        }
      } catch (e) {
        console.warn("[TEC Engine] AndroidBridge failed for " + filename + ", trying fetch");
      }
    }

    // Strategy 2: fetch()
    return fetch(url)
      .then(function (resp) {
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        return resp.json();
      })
      .then(function (data) {
        putInCache(filename, data);
        return data;
      })
      .catch(function () {
        // Strategy 3: XMLHttpRequest
        return new Promise(function (resolve, reject) {
          var xhr = new XMLHttpRequest();
          xhr.open("GET", url, true);
          xhr.responseType = "json";
          xhr.onload = function () {
            if (xhr.status === 200 || xhr.status === 0) {
              try {
                var data = xhr.response || JSON.parse(xhr.responseText);
                putInCache(filename, data);
                resolve(data);
              } catch (e) {
                reject(e);
              }
            } else {
              reject(new Error("XHR HTTP " + xhr.status));
            }
          };
          xhr.onerror = function () {
            reject(new Error("Network error: " + url));
          };
          xhr.send();
        });
      });
  }

  function tecToGeoJSON(tecMap, year, doy, utHour) {
    var features = [];
    for (var i = 0; i < N_LAT; i++) {
      for (var j = 0; j < N_LON; j++) {
        var lat = LATS[i];
        var lon = LONS[j];
        var tecValue = tecMap[i * N_LON + j];
        features.push({
          type: "Feature",
          geometry: {
            type: "Point",
            coordinates: [lon, lat],
          },
          properties: {
            tec: Math.round(tecValue * 100) / 100,
            lat: lat,
            lon: lon,
          },
        });
      }
    }

    var timeTag = year + "-" + pad3(doy) + "T" + pad2(utHour) + ":00:00Z";

    return {
      type: "FeatureCollection",
      time_tag: timeTag,
      source: "TemporalMemoryEOF-CatBoost-Offline",
      metadata: {
        year: year,
        doy: doy,
        ut_hour: utHour,
        grid: {
          lat_count: N_LAT,
          lon_count: N_LON,
          lat_min: -87.5,
          lat_max: 87.5,
          lon_min: -180,
          lon_max: 180,
        },
        unit: "TECU",
      },
      features: features,
    };
  }

  function pad3(n) {
    n = Math.floor(n);
    if (n < 10) return "00" + n;
    if (n < 100) return "0" + n;
    return "" + n;
  }

  function pad2(n) {
    n = Math.floor(n);
    if (n < 10) return "0" + n;
    return "" + n;
  }

  // ========================================================
  // Export
  // ========================================================

  root.TecEngine = TecEngine;
})(typeof window !== "undefined" ? window : globalThis);