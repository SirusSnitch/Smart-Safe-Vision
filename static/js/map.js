// Fonction d'initialisation principale
function initMap(urlConfig) {
  const saveDeptBtn = document.getElementById("save-dept-btn");

  // Fonction utilitaire pour afficher un toast avec Toastify
  function showToast(message, type = "info") {
    let bgColor = "#3498db"; // bleu
    if (type === "success") bgColor = "#27ae60"; // vert
    else if (type === "error") bgColor = "#e74c3c"; // rouge
    else if (type === "warning") bgColor = "#f39c12"; // jaune

    Toastify({
      text: message,
      duration: 4000,
      close: true,
      gravity: "top",
      position: "right",
      backgroundColor: bgColor,
      style: {
        fontWeight: 500,
        fontSize: "0.95rem",
      },
    }).showToast();
  }

  // Initialisation de la carte
  const map = L.map("map").setView([37.2367, 9.8815], 18);

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  }).addTo(map);

  L.control.scale({ position: "bottomleft", metric: true }).addTo(map);

  // Polygone ISGB
  const isgbPolygonGeoJSON = {
    type: "Feature",
    geometry: {
      type: "Polygon",
      coordinates: [
        [
          [9.882540055582894, 37.23716617665191],
          [9.880526669259268, 37.236722457011595],
          [9.88096557354379, 37.23552994753754],
          [9.882756024356922, 37.235901568792],
          [9.882978959867387, 37.236140071020344],
          [9.882547022316487, 37.2371606301723],
          [9.882540055582894, 37.23716617665191],
        ],
      ],
    },
    properties: {
      name: "ISGB",
    },
  };

  const isgbPolygon = L.geoJSON(isgbPolygonGeoJSON, {
    style: {
      color: "blue",
      weight: 3,
      fillOpacity: 0.3,
      fillColor: "blue",
    },
  }).addTo(map);

  // Calcul de la surface totale de l'ISGB
  const isgbArea = turf.area(isgbPolygonGeoJSON) / 10000; // en hectares

  // Éléments UI
  const deptList = document.getElementById("dept-list");
  const newDeptBtn = document.getElementById("new-dept-btn");
  const sidebar = document.getElementById("sidebar");
  const sidebarToggle = document.getElementById("sidebarToggle");
  const sidebarToggleMobile = document.getElementById("sidebarToggleMobile");
  const legend = document.getElementById("legend");
  const legendToggle = legend.querySelector(".legend-toggle");

  // Variables globales
  let totalArea = 0;
  let deptCount = 0;
  let drawnItems = new L.FeatureGroup();
  map.addLayer(drawnItems);
  let pendingLayer = null;

  // Configuration du contrôle de dessin
  const drawControl = new L.Control.Draw({
    position: "topleft",
    draw: {
      polygon: {
        allowIntersection: false,
        shapeOptions: {
          color: "#ff7800",
          weight: 3,
          fillOpacity: 0.4,
        },
        showArea: true,
      },
      marker: false,
      polyline: false,
      rectangle: false,
      circle: false,
      circlemarker: false,
    },
    edit: {
      featureGroup: drawnItems,
      remove: true,
    },
  });
  map.addControl(drawControl);

  // Événements UI
  newDeptBtn.addEventListener("click", () => {
    drawControl._toolbars.draw._modes.polygon.handler.enable();
    showToast(
      "Commencez à dessiner un nouveau département sur la carte",
      "info"
    );
    // Affiche le bouton Enregistrer
    saveDeptBtn.style.display = "inline-flex";
  });

  sidebarToggle.addEventListener("click", () => {
    sidebar.classList.toggle("active");
  });

  sidebarToggleMobile.addEventListener("click", () => {
    sidebar.classList.toggle("active");
  });

  legendToggle.addEventListener("click", () => {
    legend.classList.toggle("collapsed");
  });

  // Événement création polygone
  map.on(L.Draw.Event.CREATED, function (event) {
    const layer = event.layer;
    const geojson = layer.toGeoJSON();

    const isInside = turf.booleanWithin(geojson, isgbPolygonGeoJSON);

    if (!isInside) {
      showToast("Zone en dehors du périmètre ISGB !", "error");
      return;
    }

    // Stocke le layer en attente
    pendingLayer = layer;
    showToast(
      "Département dessiné. Cliquez sur 'Enregistrer' pour le valider.",
      "info"
    );
  });

  // ✅ 6. Ici tu ajoutes ton code de gestion du bouton "Enregistrer"
  saveDeptBtn.addEventListener("click", () => {
    const polygonDrawer = drawControl._toolbars.draw._modes.polygon.handler;

    // Si on est en train de dessiner, on force la fin du dessin
    if (polygonDrawer._drawing) {
      polygonDrawer.completeShape(); // Termine le dessin (équivalent de "Finish")
      polygonDrawer.disable(); // Désactive le mode dessin
    }

    // Maintenant pendingLayer devrait être défini grâce à l'événement CREATED déclenché
    if (!pendingLayer) {
      showToast("Aucun département à enregistrer", "warning");
      return;
    }

    Swal.fire({
      title: "Nom du département",
      input: "text",
      inputPlaceholder: "Entrez le nom du département",
      showCancelButton: true,
      confirmButtonText: "Enregistrer",
      cancelButtonText: "Annuler",
      inputValidator: (value) => {
        if (!value) return "Le nom est obligatoire !";
      },
    }).then((result) => {
      if (result.isConfirmed && result.value) {
        const name = result.value;
        const geojson = pendingLayer.toGeoJSON();
        const area = (turf.area(geojson) / 10000).toFixed(2);

        const feature = {
          type: "Feature",
          properties: { name, area },
          geometry: geojson.geometry,
        };

        savePolygon(feature).then((id) => {
          if (id) {
            feature.id = id;
            pendingLayer.feature = feature;
            pendingLayer.bindPopup(createPopupContent(feature));
            drawnItems.addLayer(pendingLayer);
            addDeptToSidebar(feature);
            updateStats(parseFloat(area), 1);
            showToast("Département ajouté avec succès", "success");

            pendingLayer = null;
            saveDeptBtn.style.display = "none";
          }
        });
      }
    });
  });

  // Événement édition
  map.on(L.Draw.Event.EDITED, function (e) {
    e.layers.eachLayer((layer) => {
      const geojson = layer.toGeoJSON();
      const area = (turf.area(geojson) / 10000).toFixed(2); // surface en ha
      const feature = layer.feature;

      // Met à jour la géométrie et l'aire
      feature.geometry = geojson.geometry;
      feature.properties.area = area;

      // Demande de nouveau nom via SweetAlert2 (ou prompt simple)
      Swal.fire({
        title: "Nouveau nom du département",
        input: "text",
        inputValue: feature.properties.name,
        showCancelButton: true,
        confirmButtonText: "Enregistrer",
        cancelButtonText: "Annuler",
      }).then((result) => {
        if (result.isConfirmed && result.value) {
          feature.properties.name = result.value;
          updateDeptInSidebar(feature); // <-- Mise à jour immédiate côté UI

          // Enregistre les modifications
          updatePolygon(feature).then(() => {
            layer.setPopupContent(createPopupContent(feature));
            updateDeptInSidebar(feature);
            updateStats(area, 0);
            showToast("Département modifié avec succès", "success");
          });
        } else {
          showToast("Modification annulée", "warning");
        }
      });
    });
  });

  // Événement suppression
  map.on(L.Draw.Event.DELETED, function (e) {
    e.layers.eachLayer((layer) => {
      const feature = layer.feature;
      if (feature && feature.id) {
        deletePolygon(feature.id).then((success) => {
          if (success) {
            drawnItems.removeLayer(layer);
            removeDeptFromSidebar(feature.id);
            updateStats(-parseFloat(feature.properties.area), -1);
            showToast("Département supprimé avec succès", "success");
          } else {
            showToast("Erreur lors de la suppression", "error");
          }
        });
      }
    });
  });

  // Créer le contenu du popup
  function createPopupContent(feature) {
    return `<div class="popup-content">
                <h4>${feature.properties.name}</h4>
                <p><i class="fas fa-ruler-combined"></i> Superficie: ${feature.properties.area} ha</p>
                <div class="popup-actions">
                    <button class="btn edit-btn"><i class="fas fa-edit"></i> Modifier</button>
                    <button class="btn delete-btn"><i class="fas fa-trash"></i> Supprimer</button>
                </div>
                
            </div>`;
  }

  // Ajouter un département à la sidebar
  function addDeptToSidebar(feature) {
    const deptItem = document.createElement("div");
    deptItem.className = "dept-item";
    deptItem.dataset.id = feature.id;

    const now = new Date();
    const dateStr = now.toLocaleDateString();

    deptItem.innerHTML = `
                <div class="dept-header">
                    <div class="dept-name">${feature.properties.name}</div>
                    <div class="dept-area">${feature.properties.area} ha</div>
                </div>
                <div class="dept-meta">
                    <span>Créé: ${dateStr}</span>
                    <span>Modifié: ${dateStr}</span>
                </div>
            `;

    deptItem.addEventListener("click", () => {
      // Centrer la carte sur le polygone et ouvrir le popup
      const layer = findLayerById(feature.id);
      if (layer) {
        map.fitBounds(layer.getBounds());
        layer.openPopup();
      }
    });

    deptList.appendChild(deptItem);
  }

  // Mettre à jour un département dans la sidebar
  function updateDeptInSidebar(feature) {
    const deptItem = document.querySelector(
      `.dept-item[data-id="${feature.id}"]`
    );
    if (deptItem) {
      const nameEl = deptItem.querySelector(".dept-name");
      const areaEl = deptItem.querySelector(".dept-area");
      const modifiedEl = deptItem.querySelector(".dept-meta span:last-child");

      if (nameEl) nameEl.textContent = feature.properties.name;
      if (areaEl) areaEl.textContent = `${feature.properties.area} ha`;
      if (modifiedEl)
        modifiedEl.textContent = `Modifié: ${new Date().toLocaleDateString()}`;
    }
  }

  // Supprimer un département de la sidebar
  function removeDeptFromSidebar(id) {
    const deptItem = document.querySelector(`.dept-item[data-id="${id}"]`);
    if (deptItem) {
      deptItem.remove();
    }
  }

  // Trouver un layer par son ID
  function findLayerById(id) {
    let targetLayer = null;
    drawnItems.eachLayer((layer) => {
      if (layer.feature && layer.feature.id === id) {
        targetLayer = layer;
      }
    });
    return targetLayer;
  }

  // Mettre à jour les statistiques
  function updateStats(areaChange, countChange) {
    totalArea = parseFloat((totalArea + areaChange).toFixed(2));
    deptCount += countChange;

    const coverage =
      totalArea > 0
        ? Math.min(100, Math.round((totalArea / isgbArea) * 100))
        : 0;

    document.getElementById("dept-count").textContent = deptCount;
    document.getElementById("total-area").textContent = `${totalArea} ha`;
    document.getElementById("coverage").textContent = `${coverage}%`;
  }

  // Chargement polygones existants
  function loadPolygons() {
    fetch(urlConfig.getPolygons)
      .then((res) => res.json())
      .then((data) => {
        // Calculer les stats initiales
        totalArea = 0;
        deptCount = data.features.length;

        data.features.forEach((feature) => {
          totalArea += parseFloat(feature.properties.area);
          addDeptToSidebar(feature);
        });

        updateStats(0, 0);

        // Ajouter les polygones à la carte
        L.geoJSON(data, {
          style: {
            color: "#ff7800",
            weight: 3,
            fillOpacity: 0.4,
          },
          onEachFeature: (feature, layer) => {
            layer.bindPopup(createPopupContent(feature));
            layer.feature = { ...feature, id: feature.id };
            drawnItems.addLayer(layer);
          },
        });
      })
      .catch((err) => {
        console.error("Erreur de chargement :", err);
        showToast("Erreur lors du chargement des départements", "error");
      });
  }

  // Sauvegarder un polygone
  function savePolygon(feature) {
    return fetch(urlConfig.savePolygon, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCookie("csrftoken"),
      },
      body: JSON.stringify({
        name: feature.properties.name,
        area: feature.properties.area,
        geometry: feature.geometry,
      }),
    })
      .then((res) => res.json())
      .then((data) => data.id)
      .catch((err) => {
        console.error("Erreur ajout :", err);
        showToast("Erreur lors de l'ajout du département", "error");
        return null;
      });
  }

  // Mettre à jour un polygone
  function updatePolygon(feature) {
    return fetch(urlConfig.savePolygon, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCookie("csrftoken"),
      },
      body: JSON.stringify({
        id: feature.id,
        name: feature.properties.name,
        area: feature.properties.area,
        geometry: feature.geometry,
      }),
    }).catch((err) => {
      console.error("Erreur modification :", err);
      showToast("Erreur lors de la modification du département", "error");
    });
  }

  // Supprimer un polygone
  function deletePolygon(id) {
    return fetch(urlConfig.deletePolygon(id), {
      method: "DELETE",
      headers: {
        "X-CSRFToken": getCookie("csrftoken"),
      },
    })
      .then((res) => res.ok)
      .catch((err) => {
        console.error("Erreur suppression :", err);
        showToast("Erreur lors de la suppression du département", "error");
        return false;
      });
  }

  // Récupérer le cookie CSRF (Django)
  function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(";").shift();
  }

  // Initialisation
  loadPolygons();

  // Gestion des clics sur les boutons dans les popups - CORRIGÉ
  // À mettre dans ta fonction initMap, remplace la partie map.on("popupopen", ...) par ceci :

  map.on("popupopen", (e) => {
    const popup = e.popup;
    const content = popup.getElement();
    const layer = e.popup._source;

    // Nettoyer tout ancien gestionnaire sur ce popup pour éviter doublons
    content.onclick = null;

    content.addEventListener("click", function (evt) {
      // Bouton Modifier
      if (evt.target.closest(".edit-btn")) {
        evt.stopPropagation();
        popup.remove();

        if (layer.editing) {
          layer.editing.enable();
        }

        // Création du bouton "Enregistrer"
        const saveBtn = L.DomUtil.create("button", "leaflet-bar save-edit-btn");
        saveBtn.innerHTML = '<i class="fas fa-save"></i> Enregistrer';
        Object.assign(saveBtn.style, {
          position: "absolute",
          top: "100px",
          left: "10px",
          zIndex: "1001",
          background: "#27ae60",
          color: "white",
          padding: "8px 12px",
          border: "none",
          borderRadius: "6px",
          cursor: "pointer",
          boxShadow: "0 2px 6px rgba(0,0,0,0.3)",
          fontWeight: "600",
        });
        document.body.appendChild(saveBtn);

        saveBtn.addEventListener("click", () => {
          if (layer.editing) {
            layer.editing.disable();
          }

          const geojson = layer.toGeoJSON();
          const area = (turf.area(geojson) / 10000).toFixed(2);
          const feature = layer.feature;

          feature.geometry = geojson.geometry;
          feature.properties.area = area;

          Swal.fire({
            title: "Nouveau nom du département",
            input: "text",
            inputValue: feature.properties.name,
            showCancelButton: true,
            confirmButtonText: "Enregistrer",
            cancelButtonText: "Annuler",
          }).then((result) => {
            if (result.isConfirmed && result.value) {
              feature.properties.name = result.value;

              updatePolygon(feature).then(() => {
                layer.bindPopup(createPopupContent(feature));
                updateDeptInSidebar(feature);
                updateStats(0, 0);
                showToast("Modifications enregistrées", "success");
              });
            } else {
              showToast("Modification annulée", "warning");
            }
          });

          saveBtn.remove();
        });
      }

      // Bouton Supprimer
      if (evt.target.closest(".delete-btn")) {
        evt.stopPropagation();
        const id = layer.feature.id;

        Swal.fire({
          title: "Confirmer la suppression",
          text: "Êtes-vous sûr de vouloir supprimer ce département ?",
          icon: "warning",
          showCancelButton: true,
          confirmButtonColor: "#e74c3c",
          confirmButtonText: "Oui, supprimer",
          cancelButtonText: "Annuler",
        }).then((result) => {
          if (result.isConfirmed) {
            deletePolygon(id).then((success) => {
              if (success) {
                // Ne supprimer le layer QUE si succès serveur
                drawnItems.removeLayer(layer);
                removeDeptFromSidebar(id);
                updateStats(-parseFloat(layer.feature.properties.area), -1);
                showToast("Département supprimé", "success");
              } else {
                showToast("Erreur lors de la suppression", "error");
              }
            });
          }
        });
      }
    });
  });

  // Layer group to hold camera markers
  const cameraLayer = L.layerGroup().addTo(map);

  // Function to load and display cameras as markers
  function loadCameras() {
    fetch(urlConfig.getCameras)
      .then((res) => res.json())
      .then((data) => {
        cameraLayer.clearLayers(); // clear old markers

        const cameraList = document.getElementById("camera-list");
        cameraList.innerHTML = ""; // clear old camera list

        if (data.features && data.features.length) {
          data.features.forEach((feature) => {
            const coords = feature.geometry.coordinates;
            const props = feature.properties;

            // Create marker
            const marker = L.marker([coords[1], coords[0]], {
              title: props.name,
              icon: L.icon({
                iconUrl:
                  "https://cdn-icons-png.flaticon.com/512/2499/2499215.png",
                iconSize: [30, 30],
                iconAnchor: [15, 30],
                popupAnchor: [0, -30],
              }),
            });
            marker.bindPopup(`
  <div style="width: 320px; height: 240px;">
    <strong>${props.name}</strong><br>
    <video width="300" height="200" controls autoplay data-src="${props.rtsp_url}" muted></video>
    <p style="font-size: 0.85em; color: gray;">${props.rtsp_url}</p>
  </div>
`);

            cameraLayer.addLayer(marker);

            // Add marker reference to props for sidebar interaction
            props.marker = marker;

            // Add to sidebar list
            addCameraToSidebar(props);
          });
        }
      })
      .catch((err) => {
        console.error("Erreur chargement caméras:", err);
        showToast("Erreur lors du chargement des caméras", "error");
      });
  }
  map.on("popupopen", function (e) {
    const popupEl = e.popup.getElement();
    const video = popupEl.querySelector("video");

    if (!video) return;

    const streamUrl = video.getAttribute("data-src");

    if (Hls.isSupported()) {
      const hls = new Hls();
      hls.loadSource(streamUrl);
      hls.attachMedia(video);
      hls.on(Hls.Events.MANIFEST_PARSED, function () {
        video.play();
      });
    } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
      video.src = streamUrl;
      video.addEventListener("loadedmetadata", () => {
        video.play();
      });
    } else {
      popupEl.innerHTML +=
        "<p style='color:red'>Votre navigateur ne supporte pas le streaming HLS.</p>";
    }
  });

  function deleteCamera(id) {
    return fetch(`/delete_camera/${id}/`, {
      method: "DELETE",
      headers: {
        "X-CSRFToken": getCookie("csrftoken"),
      },
    })
      .then((res) => res.ok)
      .catch((err) => {
        console.error("Erreur suppression caméra :", err);
        return false;
      });
  }

  function addCameraToSidebar(camera) {
    const cameraList = document.getElementById("camera-list");

    const cameraItem = document.createElement("div");
    cameraItem.className = "camera-item";
    cameraItem.dataset.id = camera.id;

    cameraItem.innerHTML = `
  <div class="camera-name">${camera.name}</div>
  <div class="camera-department">${
    camera.department_name || "Aucun département"
  }</div>
  <a href="${camera.url}" target="_blank" class="camera-link">Voir la caméra</a>
  <button class="btn btn-edit-camera" title="Modifier la caméra" style="margin-left: 10px; color: green; border: none; background: transparent; cursor: pointer;">
    <i class="fas fa-edit"></i>
  </button>
  <button class="btn btn-delete-camera" title="Supprimer la caméra" style="margin-left: 10px; color: red; border: none; background: transparent; cursor: pointer;">
    <i class="fas fa-trash"></i>
  </button>
`;

    // Click on item centers map on marker and opens popup
    cameraItem.addEventListener("click", (e) => {
      // Prevent delete button click from triggering this event
      if (e.target.closest(".btn-delete-camera")) return;

      if (camera.marker) {
        map.setView(camera.marker.getLatLng(), 20);
        camera.marker.openPopup();
      }
    });

    // Delete button handler
    const deleteBtn = cameraItem.querySelector(".btn-delete-camera");
    deleteBtn.addEventListener("click", (e) => {
      e.stopPropagation(); // Prevent triggering parent click event

      Swal.fire({
        title: "Confirmer la suppression",
        text: `Voulez-vous supprimer la caméra "${camera.name}" ?`,
        icon: "warning",
        showCancelButton: true,
        confirmButtonColor: "#e74c3c",
        confirmButtonText: "Oui, supprimer",
        cancelButtonText: "Annuler",
      }).then((result) => {
        if (result.isConfirmed) {
          deleteCamera(camera.id).then((success) => {
            if (success) {
              // Remove marker from map
              if (camera.marker) {
                cameraLayer.removeLayer(camera.marker);
              }
              // Remove camera from sidebar list
              cameraItem.remove();

              showToast("Caméra supprimée avec succès", "success");
            } else {
              showToast("Erreur lors de la suppression", "error");
            }
          });
        }
      });
    });

    // Edit button handler
    const editBtn = cameraItem.querySelector(".btn-edit-camera");
    editBtn.addEventListener("click", (e) => {
      e.stopPropagation();

      Swal.fire({
        title: "Modifier la caméra",
        html: `
      <input id="cam-edit-name" class="swal2-input" placeholder="Nom de la caméra" value="${camera.name}">
      <input id="cam-edit-url" class="swal2-input" placeholder="URL de la caméra" value="${camera.url}">
      <button id="move-camera-btn" class="swal2-confirm swal2-styled" style="background:#f39c12; margin-top:5px;">
        <i class="fas fa-arrows-alt"></i> Déplacer la caméra
      </button>
    `,
        focusConfirm: false,
        showCancelButton: true,
        confirmButtonText: "Enregistrer",
        preConfirm: () => {
          const name = document.getElementById("cam-edit-name").value.trim();
          const url = document.getElementById("cam-edit-url").value.trim();
          if (!name || !url) {
            Swal.showValidationMessage("Tous les champs sont requis");
          }
          return { name, url };
        },
        didOpen: () => {
          const moveBtn = document.getElementById("move-camera-btn");
          moveBtn.addEventListener("click", () => {
            Swal.close();
            showToast("Cliquez sur la carte pour placer la caméra", "info");

            drawnItems.eachLayer((layer) => {
              layer.off("click");
            });

            map.once("click", (event) => {
              const newLatLng = event.latlng;

              fetch("/save_camera/", {
                method: "POST",
                headers: {
                  "Content-Type": "application/json",
                  "X-CSRFToken": getCookie("csrftoken"),
                },
                body: JSON.stringify({
                  id: camera.id,
                  name: camera.name,
                  url: camera.url,
                  coordinates: [newLatLng.lng, newLatLng.lat],
                }),
              })
                .then((res) => res.json())
                .then((data) => {
                  if (data.status === "success") {
                    showToast("Caméra déplacée avec succès", "success");
                    loadCameras(); // refresh markers and sidebar

                    drawnItems.eachLayer((layer) => {
                      layer.on("click", () => {
                        layer.openPopup();
                      });
                    });
                  } else {
                    showToast(
                      "Erreur : " + (data.message || "Erreur inconnue"),
                      "error"
                    );
                  }
                })
                .catch((err) => {
                  console.error("Erreur réseau:", err);
                  showToast("Erreur réseau lors du déplacement", "error");
                });
            });
          });
        },
      }).then((result) => {
        if (result.isConfirmed) {
          const { name, url } = result.value;

          fetch("/save_camera/", {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-CSRFToken": getCookie("csrftoken"),
            },
            body: JSON.stringify({
              id: camera.id, // Utilisation de l'id pour l'update
              name,
              url,
              coordinates: [
                camera.marker.getLatLng().lng,
                camera.marker.getLatLng().lat,
              ],
            }),
          })
            .then((res) => res.json())
            .then((data) => {
              if (data.status === "success") {
                showToast("Caméra modifiée avec succès", "success");
                loadCameras(); // refresh
              } else if (data.status === "error") {
                showToast(
                  "Erreur : " + (data.message || "Erreur inconnue"),
                  "error"
                );
              } else {
                showToast("Erreur inattendue lors de la modification", "error");
              }
            })
            .catch((err) => {
              console.error("Erreur modification caméra :", err);
              showToast("Erreur réseau lors de la modification", "error");
            });
        }
      });
    });

    cameraList.appendChild(cameraItem);
  }

  loadCameras();

  const newCameraBtn = document.getElementById("new-camera-btn");
  const saveCameraBtn = document.getElementById("save-camera-btn");
  let pendingCameraLatLng = null;

  // Quand on clique sur "Nouvelle caméra"
  newCameraBtn.addEventListener("click", () => {
    showToast("Cliquez sur la carte pour placer la caméra", "info");
    saveCameraBtn.style.display = "inline-flex";
    // Désactiver l'ouverture popup des départements pendant ajout caméra
    drawnItems.eachLayer((layer) => {
      layer.off("click"); // désactive le clic qui ouvre popup
    });

    map.once("click", (e) => {
      pendingCameraLatLng = e.latlng;

      Swal.fire({
        title: "Nouvelle caméra",
        html: `
        <input id="cam-name" class="swal2-input" placeholder="Nom de la caméra">
        <input id="cam-url" class="swal2-input" placeholder="URL de la caméra">
      `,
        focusConfirm: false,
        showCancelButton: true,
        confirmButtonText: "Valider",
        preConfirm: () => {
          const name = document.getElementById("cam-name").value.trim();
          const url = document.getElementById("cam-url").value.trim();
          if (!name || !url) {
            Swal.showValidationMessage("Tous les champs sont requis");
          }
          return { name, url };
        },
      }).then((result) => {
        if (result.isConfirmed) {
          const { name, url } = result.value;

          const coordinates = [
            pendingCameraLatLng.lng,
            pendingCameraLatLng.lat,
          ];

          fetch("/save_camera/", {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-CSRFToken": getCookie("csrftoken"),
            },
            body: JSON.stringify({
              name,
              url,
              coordinates,
            }),
          })
            .then((res) => res.json())
            .then((data) => {
              if (data.status === "success") {
                showToast("Caméra ajoutée avec succès", "success");
                loadCameras(); // recharger les caméras
              } else if (data.status === "error") {
                // Ici on affiche le message personnalisé envoyé par le serveur
                showToast(
                  "Erreur : " + (data.message || "Erreur inconnue"),
                  "error"
                );
              } else {
                showToast("Erreur inattendue lors de l'ajout", "error");
              }
            });

          saveCameraBtn.style.display = "none";
          pendingCameraLatLng = null;
        }
      });
    });
  });
}