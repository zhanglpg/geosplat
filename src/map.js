/**
 * Map Module — 2D map overlay for geospatial context
 * Uses MapLibre GL JS (open-source, no API key needed for basic usage)
 */

import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';

// Scene origin in WGS84
let origin = { lat: 30.25, lng: 120.12, alt: 50 };
let map = null;
let sceneMarker = null;
let cameraMarker = null;

/**
 * Initialize the map overlay.
 * @param {HTMLElement} container - DOM element to mount the map
 * @param {{lat: number, lng: number, alt: number}} geoOrigin - GPS origin of the 3D scene
 */
export function initMap(container, geoOrigin = null) {
  if (geoOrigin) origin = geoOrigin;

  map = new maplibregl.Map({
    container,
    style: 'https://demotiles.maplibre.org/style.json', // free OSM-based style
    center: [origin.lng, origin.lat],
    zoom: 15,
    attributionControl: false,
  });

  map.on('load', () => {
    // Scene origin marker
    const el = document.createElement('div');
    el.style.width = '16px';
    el.style.height = '16px';
    el.style.borderRadius = '50%';
    el.style.background = '#ff4444';
    el.style.border = '2px solid white';
    el.style.boxShadow = '0 0 4px rgba(0,0,0,0.5)';

    sceneMarker = new maplibregl.Marker({ element: el })
      .setLngLat([origin.lng, origin.lat])
      .addTo(map);

    // Camera position marker
    const camEl = document.createElement('div');
    camEl.style.width = '10px';
    camEl.style.height = '10px';
    camEl.style.borderRadius = '50%';
    camEl.style.background = '#44aaff';
    camEl.style.border = '2px solid white';

    cameraMarker = new maplibregl.Marker({ element: camEl })
      .setLngLat([origin.lng, origin.lat])
      .addTo(map);
  });

  return map;
}

/**
 * Update camera indicator on the map based on 3D camera position.
 * @param {number} x - Camera X in scene space (meters east)
 * @param {number} z - Camera Z in scene space (meters north)
 * @param {number} heading - Camera heading in degrees (0=north, 90=east)
 */
export function updateCameraOnMap(x, z, heading = 0) {
  if (!map || !cameraMarker) return;

  const metersPerDegLat = 111320;
  const metersPerDegLng = 111320 * Math.cos(origin.lat * Math.PI / 180);

  const lat = origin.lat + z / metersPerDegLat;
  const lng = origin.lng + x / metersPerDegLng;

  cameraMarker.setLngLat([lng, lat]);
  cameraMarker.setRotation(-heading);
}

/**
 * Set the geospatial origin of the scene.
 */
export function setOrigin(lat, lng, alt = 0) {
  origin = { lat, lng, alt };
  if (map) {
    map.setCenter([lng, lat]);
    sceneMarker?.setLngLat([lng, lat]);
  }
}

/**
 * Dispose map resources.
 */
export function dispose() {
  map?.remove();
  map = null;
}
