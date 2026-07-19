// VeriMed AI -- frontend logic
// Wires the checker, predictor, and passport pages to the Flask API.

// ---------- Helpers ----------

function verdictColorClasses(verdict) {
    switch ((verdict || "").toLowerCase()) {
        case "true":
            return { badge: "bg-emerald-50 border-emerald-200 text-emerald-700", bar: "bg-emerald-600" };
        case "false":
            return { badge: "bg-red-50 border-red-200 text-red-700", bar: "bg-red-600" };
        case "misleading":
            return { badge: "bg-amber-50 border-amber-200 text-amber-700", bar: "bg-amber-600" };
        default:
            return { badge: "bg-slate-50 border-slate-200 text-slate-700", bar: "bg-slate-500" };
    }
}

// ---------- Emergency Help page ----------

const useGpsBtn = document.getElementById("useGpsBtn");
if (useGpsBtn) {
    const manualSearchBtn = document.getElementById("manualSearchBtn");
    const manualLocationInput = document.getElementById("manualLocationInput");
    const hospitalStatus = document.getElementById("hospitalStatus");
    const hospitalList = document.getElementById("hospitalList");

    function setStatus(message, isError = false) {
        hospitalStatus.textContent = message;
        hospitalStatus.className = isError
            ? "text-sm text-red-500 text-center py-6"
            : "text-sm text-slate-400 text-center py-6";
    }

    function showOfflineNotice() {
        hospitalList.innerHTML = `
            <div class="md:col-span-2 bg-amber-50 border border-amber-200 rounded-2xl p-4 text-sm text-amber-700">
                <strong>Location lookup is unavailable in this browser right now.</strong>
                <p class="mt-1">Please use a desktop browser with location access or manually type a nearby city or area name.</p>
            </div>`;
    }

    function haversineDistanceKm(lat1, lon1, lat2, lon2) {
        const R = 6371;
        const dLat = ((lat2 - lat1) * Math.PI) / 180;
        const dLon = ((lon2 - lon1) * Math.PI) / 180;
        const a =
            Math.sin(dLat / 2) ** 2 +
            Math.cos((lat1 * Math.PI) / 180) *
                Math.cos((lat2 * Math.PI) / 180) *
                Math.sin(dLon / 2) ** 2;
        return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    }

    function buildAddress(tags) {
        const parts = [
            tags["addr:housenumber"],
            tags["addr:street"],
            tags["addr:suburb"],
            tags["addr:city"],
            tags["addr:postcode"],
        ].filter(Boolean);
        return parts.length ? parts.join(", ") : "Address not available";
    }

    async function fetchNearbyHospitals(lat, lon) {
        hospitalList.innerHTML = "";
        setStatus("Searching for hospitals and clinics nearby...");

        // Overpass API (OpenStreetMap) -- free, no API key required
        const query = `
            [out:json][timeout:25];
            (
              node["amenity"="hospital"](around:6000,${lat},${lon});
              way["amenity"="hospital"](around:6000,${lat},${lon});
              node["amenity"="clinic"](around:6000,${lat},${lon});
              way["amenity"="clinic"](around:6000,${lat},${lon});
            );
            out center 40;
        `;

        try {
            const res = await fetch("https://overpass-api.de/api/interpreter", {
                method: "POST",
                body: "data=" + encodeURIComponent(query),
            });
            if (!res.ok) throw new Error("Overpass API request failed.");
            const data = await res.json();

            const results = (data.elements || [])
                .filter((el) => el.tags && el.tags.name)
                .map((el) => {
                    const elLat = el.lat || (el.center && el.center.lat);
                    const elLon = el.lon || (el.center && el.center.lon);
                    return {
                        name: el.tags.name,
                        type: el.tags.amenity === "hospital" ? "Hospital" : "Clinic",
                        address: buildAddress(el.tags),
                        phone: el.tags.phone || el.tags["contact:phone"] || null,
                        lat: elLat,
                        lon: elLon,
                        distanceKm: elLat && elLon ? haversineDistanceKm(lat, lon, elLat, elLon) : null,
                    };
                })
                .filter((h) => h.lat && h.lon)
                .sort((a, b) => (a.distanceKm ?? 999) - (b.distanceKm ?? 999))
                .slice(0, 20);

            if (results.length === 0) {
                setStatus("No hospitals found nearby. Try a different location.", true);
                return;
            }

            setStatus(`Found ${results.length} hospitals/clinics nearby, sorted by distance.`);
            renderHospitalList(results);
        } catch (err) {
            setStatus("Couldn't fetch nearby hospitals. Please try again.", true);
        }
    }

    function renderHospitalList(hospitals) {
        hospitalList.innerHTML = hospitals
            .map((h) => {
                const directionsUrl = `https://www.google.com/maps/dir/?api=1&destination=${h.lat},${h.lon}`;
                const distanceLabel = h.distanceKm !== null ? `${h.distanceKm.toFixed(1)} km away` : "";
                return `
                <div class="bg-slate-50 border border-slate-100 rounded-2xl p-4">
                    <div class="flex items-start justify-between gap-2">
                        <div>
                            <h4 class="font-bold text-slate-800">${escapeHtml(h.name)}</h4>
                            <span class="inline-block text-[10px] font-bold uppercase tracking-wide text-blue-600 bg-blue-50 px-2 py-0.5 rounded-full mt-1">${escapeHtml(h.type)}</span>
                            ${distanceLabel ? `<span class="text-xs text-slate-400 ml-2">${distanceLabel}</span>` : ""}
                        </div>
                    </div>
                    <p class="text-xs text-slate-500 mt-2">${escapeHtml(h.address)}</p>
                    <div class="flex gap-2 mt-3">
                        ${h.phone ? `<a href="tel:${escapeHtml(h.phone)}" class="flex-1 text-center bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold py-2 rounded-lg transition-colors"><i class="fa-solid fa-phone mr-1"></i>Call</a>` : ""}
                        <a href="${directionsUrl}" target="_blank" class="flex-1 text-center bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold py-2 rounded-lg transition-colors"><i class="fa-solid fa-location-arrow mr-1"></i>Directions</a>
                    </div>
                </div>`;
            })
            .join("");
    }

    useGpsBtn.addEventListener("click", () => {
        if (!navigator.geolocation) {
            setStatus("Your browser doesn't support GPS location.", true);
            showOfflineNotice();
            return;
        }
        setStatus("Requesting your location...");
        navigator.geolocation.getCurrentPosition(
            (position) => {
                fetchNearbyHospitals(position.coords.latitude, position.coords.longitude);
            },
            () => {
                setStatus("Location access denied. Try typing a location manually instead.", true);
                showOfflineNotice();
            }
        );
    });

    async function searchManualLocation() {
        const query = manualLocationInput.value.trim();
        if (!query) return;

        setStatus(`Looking up "${query}"...`);
        try {
            // Nominatim (OpenStreetMap) geocoding -- free, no API key required
            const res = await fetch(
                `https://nominatim.openstreetmap.org/search?format=json&limit=1&q=${encodeURIComponent(query)}`,
                { headers: { "Accept": "application/json" } }
            );
            const results = await res.json();
            if (!results || results.length === 0) {
                setStatus(`Couldn't find "${query}". Try a more specific location.`, true);
                return;
            }
            const { lat, lon } = results[0];
            fetchNearbyHospitals(parseFloat(lat), parseFloat(lon));
        } catch (err) {
            setStatus("Location search failed. Please try again.", true);
        }
    }

    manualSearchBtn.addEventListener("click", searchManualLocation);
    manualLocationInput.addEventListener("keypress", (e) => {
        if (e.key === "Enter") searchManualLocation();
    });
}

// ---------- Checker page ----------

const checkerForm = document.getElementById("checkerForm");
if (checkerForm) {
    const imageInput = document.getElementById("imageInput");
    const fileNameLabel = document.getElementById("fileName");

    if (imageInput) {
        imageInput.addEventListener("change", () => {
            if (imageInput.files.length > 0) {
                fileNameLabel.textContent = `Selected: ${imageInput.files[0].name}`;
            }
        });
    }

    // ---- Voice-to-text (Web Speech API -- browser-native, no API key) ----
    const voiceBtn = document.getElementById("voiceInputBtn");
    const voiceLabel = document.getElementById("voiceInputLabel");
    const claimTextarea = document.getElementById("claimTextarea");
    const SpeechRecognitionAPI = window.SpeechRecognition || window.webkitSpeechRecognition;

    function mapSpeechLanguage(code) {
        const langMap = { en: "en-US", hi: "hi-IN", mr: "mr-IN", es: "es-ES" };
        return langMap[code] || "en-US";
    }

    if (voiceBtn && SpeechRecognitionAPI) {
        const recognition = new SpeechRecognitionAPI();
        recognition.continuous = false;
        recognition.interimResults = false;
        recognition.maxAlternatives = 1;
        let isListening = false;

        const setListeningState = (listening) => {
            isListening = listening;
            voiceBtn.classList.toggle("text-red-600", listening);
            voiceLabel.textContent = listening ? "Listening..." : "Speak";
        };

        voiceBtn.addEventListener("click", () => {
            if (isListening) {
                recognition.stop();
                return;
            }

            const langSelect = checkerForm.querySelector("select[name='language']");
            recognition.lang = mapSpeechLanguage(langSelect ? langSelect.value : "en");

            try {
                recognition.start();
                setListeningState(true);
            } catch (err) {
                setListeningState(false);
            }
        });

        recognition.addEventListener("result", (event) => {
            const transcript = Array.from(event.results)
                .map((result) => result[0]?.transcript || "")
                .join(" ")
                .trim();

            if (transcript) {
                claimTextarea.value = (claimTextarea.value ? `${claimTextarea.value} ${transcript}`.trim() : transcript);
            }
        });

        recognition.addEventListener("end", () => {
            setListeningState(false);
        });

        recognition.addEventListener("error", (event) => {
            console.warn("Speech recognition error:", event.error);
            setListeningState(false);
        });
    } else if (voiceBtn) {
        // Browser doesn't support Speech Recognition (e.g. Firefox) -- hide gracefully
        voiceBtn.style.display = "none";
    }

    checkerForm.addEventListener("submit", async (e) => {
        e.preventDefault();

        const submitBtn = checkerForm.querySelector("button[type='submit']");
        const originalBtnHtml = submitBtn.innerHTML;
        submitBtn.disabled = true;
        submitBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Analyzing...`;

        const placeholder = document.getElementById("resultsPlaceholder");
        const resultsCard = document.getElementById("resultsCard");

        try {
            const formData = new FormData(checkerForm);
            const res = await fetch("/api/verify", { method: "POST", body: formData });
            const data = await res.json();

            if (!res.ok) {
                throw new Error(data.explanation || data.error || "Verification failed.");
            }

            renderCheckerResult(data);
            placeholder.classList.add("hidden");
            resultsCard.classList.remove("hidden");
        } catch (err) {
            placeholder.classList.remove("hidden");
            resultsCard.classList.add("hidden");
            placeholder.innerHTML = `
                <i class="fa-solid fa-triangle-exclamation text-4xl mb-3 text-red-400"></i>
                <p class="font-bold text-sm text-red-500">${escapeHtml(err.message)}</p>
            `;
        } finally {
            submitBtn.disabled = false;
            submitBtn.innerHTML = originalBtnHtml;
        }
    });
}

function renderCheckerResult(data) {
    const colors = verdictColorClasses(data.verdict);

    const verdictBadge = document.getElementById("verdictBadge");
    verdictBadge.className = `p-5 rounded-2xl border flex flex-col gap-2 ${colors.badge}`;

    // If the claim came from an uploaded screenshot, show the OCR'd text so
    // the user can confirm it was read correctly before trusting the verdict.
    let ocrNote = "";
    const existingOcrNote = document.getElementById("ocrExtractedNote");
    if (existingOcrNote) existingOcrNote.remove();
    if (data.ocr_used && data.claim_text_used) {
        ocrNote = document.createElement("div");
        ocrNote.id = "ocrExtractedNote";
        ocrNote.className = "text-[11px] font-semibold text-slate-500 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 mb-1";
        ocrNote.innerHTML = `<i class="fa-solid fa-text-height mr-1"></i> Text read from image: "${escapeHtml(data.claim_text_used)}"`;
        verdictBadge.parentElement.insertBefore(ocrNote, verdictBadge);
    }

    document.getElementById("verdictLabel").textContent = data.verdict || "Unverified";
    document.getElementById("explanationText").textContent = data.explanation || "";

    const confidence = Number(data.confidence) || 0;
    document.getElementById("confidenceValue").textContent = `${confidence}%`;
    const bar = document.getElementById("confidenceBar");
    bar.style.width = `${confidence}%`;
    bar.className = `h-full transition-all duration-500 ${colors.bar}`;

    const entityContainer = document.getElementById("entityContainer");
    entityContainer.innerHTML = "";
    (data.entities || []).forEach((ent) => {
        const chip = document.createElement("span");
        chip.className = "text-[11px] font-bold bg-blue-50 text-blue-700 px-2.5 py-1 rounded-full border border-blue-100";
        chip.textContent = `${ent.text} · ${ent.label}`;
        entityContainer.appendChild(chip);
    });
    if (!data.entities || data.entities.length === 0) {
        entityContainer.innerHTML = `<span class="text-xs text-slate-400">No entities detected.</span>`;
    }

    const sourceContainer = document.getElementById("sourceContainer");
    sourceContainer.innerHTML = "";
    (data.sources || []).forEach((src) => {
        const line = document.createElement("div");
        line.innerHTML = `<i class="fa-solid fa-check text-emerald-500 mr-1"></i> ${escapeHtml(src)}`;
        sourceContainer.appendChild(line);
    });
    if (!data.sources || data.sources.length === 0) {
        sourceContainer.innerHTML = `<span class="text-xs text-slate-400">No sources returned.</span>`;
    }

    document.getElementById("shareVerdict").textContent = `Verdict: ${data.verdict || "Unverified"}`;
    document.getElementById("shareExplanation").textContent = data.explanation || "";

    // ---- Text-to-speech: read the verdict + explanation aloud ----
    const speakBtn = document.getElementById("speakResultBtn");
    const speakLabel = document.getElementById("speakResultLabel");
    if (speakBtn && "speechSynthesis" in window) {
        const SPEECH_LANG_MAP = {
            en: "en-US",
            hi: "hi-IN",
            mr: "mr-IN",
            es: "es-ES",
        };

        let speakNote = document.getElementById("speakVoiceNote");
        if (!speakNote && speakBtn.parentElement) {
            speakNote = document.createElement("div");
            speakNote.id = "speakVoiceNote";
            speakNote.className = "text-[10px] text-slate-400 mt-1 hidden";
            speakBtn.parentElement.appendChild(speakNote);
        }

        // Chrome loads its voice list asynchronously. Calling
        // getVoices() too early (e.g. the first time it's ever called on
        // a page) can return an empty array even though voices exist --
        // this waits for the real list instead of assuming it's ready.
        function loadVoicesOnce() {
            return new Promise((resolve) => {
                const existing = window.speechSynthesis.getVoices();
                if (existing.length > 0) {
                    resolve(existing);
                    return;
                }
                window.speechSynthesis.onvoiceschanged = () => {
                    resolve(window.speechSynthesis.getVoices());
                };
                // Safety timeout in case the event never fires on some browsers
                setTimeout(() => resolve(window.speechSynthesis.getVoices()), 1000);
            });
        }

        speakBtn.onclick = async () => {
            if (window.speechSynthesis.speaking || window.speechSynthesis.pending) {
                window.speechSynthesis.cancel();
                speakLabel.textContent = "Listen";
                return;
            }

            const availableVoices = await loadVoicesOnce();

            const utterance = new SpeechSynthesisUtterance(
                `Verdict: ${data.verdict}. ${data.explanation || ""}`
            );
            utterance.rate = 0.95;

            const targetLangCode = SPEECH_LANG_MAP[data.language_processed] || "en-US";
            let chosenVoice = availableVoices.find(v => v.lang === targetLangCode);

            if (!chosenVoice && data.language_processed === "mr") {
                chosenVoice = availableVoices.find(v => v.lang === "hi-IN");
            }

            if (chosenVoice) {
                utterance.voice = chosenVoice;
                utterance.lang = chosenVoice.lang;
            } else {
                utterance.lang = "en-US";
            }

            if (speakNote) {
                if (!chosenVoice) {
                    speakNote.textContent = `No voice available for this language on your device -- using default.`;
                    speakNote.classList.remove("hidden");
                } else if (chosenVoice.lang !== targetLangCode) {
                    speakNote.textContent = `No Marathi voice found on this device -- using the closest available (Hindi) voice instead.`;
                    speakNote.classList.remove("hidden");
                } else {
                    speakNote.classList.add("hidden");
                }
            }

            utterance.onstart = () => { speakLabel.textContent = "Stop"; };
            utterance.onend = () => { speakLabel.textContent = "Listen"; };
            utterance.onerror = () => { speakLabel.textContent = "Listen"; };
            window.speechSynthesis.cancel();
            window.speechSynthesis.speak(utterance);
        };
    } else if (speakBtn) {
        speakBtn.style.display = "none";
    }
}

// ---------- Predictor page ----------

async function runPredictionPipeline() {
    const input = document.getElementById("predictInput");
    const panel = document.getElementById("predictOutputPanel");
    const claim = input.value.trim();

    if (!claim) {
        panel.innerHTML = `<div class="m-auto text-center text-amber-400 font-bold text-xs">Enter a claim first.</div>`;
        return;
    }

    panel.innerHTML = `
        <div class="m-auto text-center text-slate-500 font-bold text-xs flex flex-col gap-2 items-center">
            <i class="fa-solid fa-circle-nodes text-3xl text-purple-500/50 animate-spin"></i>
            Computing spread risk signals...
        </div>
    `;

    try {
        const res = await fetch("/api/predict_spread", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ claim }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "Prediction failed.");

        const riskColor = data.risk_level === "High Risk" ? "text-red-400" : (data.risk_level === "Medium Risk" ? "text-amber-400" : "text-emerald-400");
        const breakdown = data.signal_breakdown || {};

        panel.innerHTML = `
            <div class="text-[10px] uppercase tracking-wider font-bold text-blue-400 mb-1 flex items-center gap-1.5">
                <i class="fa-solid fa-diagram-project"></i> Heuristic graph + language analysis -- not a trained model
            </div>
            <div class="grid grid-cols-2 gap-4">
                <div class="bg-slate-800/60 rounded-xl p-4">
                    <span class="text-[10px] uppercase font-bold text-slate-400">Risk Score</span>
                    <div class="text-3xl font-black mt-1">${escapeHtml(data.virality_score)}<span class="text-sm text-slate-500">/100</span></div>
                </div>
                <div class="bg-slate-800/60 rounded-xl p-4">
                    <span class="text-[10px] uppercase font-bold text-slate-400">Risk Level</span>
                    <div class="text-xl font-black mt-1 ${riskColor}">${escapeHtml(data.risk_level)}</div>
                </div>
                <div class="bg-slate-800/60 rounded-xl p-4">
                    <span class="text-[10px] uppercase font-bold text-slate-400">Estimated Reach (order of magnitude)</span>
                    <div class="text-xl font-black mt-1">${escapeHtml(data.reach_estimate_bucket)}</div>
                </div>
                <div class="bg-slate-800/60 rounded-xl p-4">
                    <span class="text-[10px] uppercase font-bold text-slate-400">Est. Time To Peak</span>
                    <div class="text-2xl font-black mt-1">${escapeHtml(data.time_to_peak_hours)}h</div>
                </div>
            </div>
            <div class="bg-slate-800/60 rounded-xl p-4">
                <span class="text-[10px] uppercase font-bold text-slate-400 block mb-2">Signal Breakdown</span>
                <div class="flex flex-col gap-2 text-xs">
                    <div class="flex justify-between"><span class="text-slate-300">Matches known misinformation pattern</span><span class="font-bold">${escapeHtml(breakdown.misinformation_pattern_match ?? "-")}</span></div>
                    <div class="flex justify-between"><span class="text-slate-300">Sensational language score</span><span class="font-bold">${escapeHtml(breakdown.sensational_language_score ?? "-")}</span></div>
                    <div class="flex justify-between"><span class="text-slate-300">Entity graph embeddedness</span><span class="font-bold">${escapeHtml(breakdown.entity_embeddedness_score ?? "-")}</span></div>
                </div>
            </div>
            <div class="text-[10px] text-slate-500 leading-relaxed px-1">
                ${escapeHtml(data.methodology || "")}
            </div>
        `;
    } catch (err) {
        panel.innerHTML = `<div class="m-auto text-center text-red-400 font-bold text-xs">${escapeHtml(err.message)}</div>`;
    }
}

// ---------- Passport page ----------

const passportForm = document.getElementById("passportForm");
if (passportForm) {
    // Load any existing saved passport on page load
    fetch("/api/passport")
        .then((res) => res.json())
        .then((data) => {
            if (!data) return;
            document.getElementById("passName").value = data.full_name || "";
            document.getElementById("passBlood").value = data.blood_group || "";
            document.getElementById("passDob").value = data.date_of_birth || "";
            document.getElementById("passAllergies").value = data.allergies || "";
            document.getElementById("passChronic").value = data.chronic_conditions || "";
            document.getElementById("passMeds").value = data.current_medicines || "";
            document.getElementById("passContact").value = data.emergency_contact_name || "";
            document.getElementById("passPhone").value = data.emergency_contact_phone || "";
            showQrCode();
        })
        .catch(() => {});

    passportForm.addEventListener("submit", async (e) => {
        e.preventDefault();

        const payload = {
            full_name: document.getElementById("passName").value,
            blood_group: document.getElementById("passBlood").value,
            date_of_birth: document.getElementById("passDob").value,
            allergies: document.getElementById("passAllergies").value,
            chronic_conditions: document.getElementById("passChronic").value,
            current_medicines: document.getElementById("passMeds").value,
            emergency_contact_name: document.getElementById("passContact").value,
            emergency_contact_phone: document.getElementById("passPhone").value,
        };

        const submitBtn = passportForm.querySelector("button[type='submit']");
        const originalText = submitBtn.textContent;
        submitBtn.disabled = true;
        submitBtn.textContent = "Saving...";

        try {
            const res = await fetch("/api/passport", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });
            if (!res.ok) throw new Error("Failed to save passport.");
            showQrCode();
        } catch (err) {
            alert(err.message);
        } finally {
            submitBtn.disabled = false;
            submitBtn.textContent = originalText;
        }
    });
}

function showQrCode() {
    const qrContainer = document.getElementById("qrContainer");
    if (!qrContainer) return;
    // Cache-bust so the browser doesn't show a stale QR after an update
    qrContainer.innerHTML = `<img src="/api/passport/qr?t=${Date.now()}" alt="Health Passport QR Code" class="w-40 h-40 object-contain" />`;
}

// ---------- Surgeries ----------

const surgeryForm = document.getElementById("surgeryForm");
if (surgeryForm) {
    function loadSurgeries() {
        fetch("/api/passport/surgeries")
            .then((res) => res.json())
            .then((surgeries) => {
                const list = document.getElementById("surgeryList");
                if (!surgeries || surgeries.length === 0) {
                    list.innerHTML = `<p class="text-xs text-slate-400 text-center py-3">No surgeries recorded yet.</p>`;
                    return;
                }
                list.innerHTML = surgeries.map((s) => `
                    <div class="flex items-center justify-between bg-slate-50 border border-slate-100 rounded-xl p-3">
                        <div><span class="font-bold text-sm text-slate-700">${escapeHtml(s.year)}</span> <span class="text-sm text-slate-500">-- ${escapeHtml(s.description)}</span></div>
                        <button onclick="deleteSurgery(${s.id})" class="text-red-400 hover:text-red-600 text-xs"><i class="fa-solid fa-trash"></i></button>
                    </div>`).join("");
            });
    }

    surgeryForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const year = document.getElementById("surgeryYear").value;
        const description = document.getElementById("surgeryDescription").value;
        await fetch("/api/passport/surgeries", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ year, description }),
        });
        surgeryForm.reset();
        loadSurgeries();
    });

    window.deleteSurgery = async (id) => {
        await fetch(`/api/passport/surgeries/${id}`, { method: "DELETE" });
        loadSurgeries();
    };

    loadSurgeries();
}

// ---------- Vaccinations ----------

const vaccinationForm = document.getElementById("vaccinationForm");
if (vaccinationForm) {
    function loadVaccinations() {
        fetch("/api/passport/vaccinations")
            .then((res) => res.json())
            .then((vaccinations) => {
                const list = document.getElementById("vaccinationList");
                if (!vaccinations || vaccinations.length === 0) {
                    list.innerHTML = `<p class="text-xs text-slate-400 text-center py-3">No vaccinations recorded yet.</p>`;
                    return;
                }
                list.innerHTML = vaccinations.map((v) => `
                    <div class="flex items-center justify-between bg-slate-50 border border-slate-100 rounded-xl p-3">
                        <div><span class="font-bold text-sm text-slate-700">${escapeHtml(v.month)} ${escapeHtml(v.year)}</span> <span class="text-sm text-slate-500">-- ${escapeHtml(v.vaccine_name)}</span></div>
                        <button onclick="deleteVaccination(${v.id})" class="text-red-400 hover:text-red-600 text-xs"><i class="fa-solid fa-trash"></i></button>
                    </div>`).join("");
            });
    }

    vaccinationForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const vaccine_name = document.getElementById("vaccineName").value;
        const month = document.getElementById("vaccineMonth").value;
        const year = document.getElementById("vaccineYear").value;
        await fetch("/api/passport/vaccinations", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ vaccine_name, month, year }),
        });
        vaccinationForm.reset();
        loadVaccinations();
    });

    window.deleteVaccination = async (id) => {
        await fetch(`/api/passport/vaccinations/${id}`, { method: "DELETE" });
        loadVaccinations();
    };

    loadVaccinations();
}

// ---------- Medical Report Uploads ----------

const reportForm = document.getElementById("reportForm");
if (reportForm) {
    function loadReports() {
        fetch("/api/passport/reports")
            .then((res) => res.json())
            .then((reports) => {
                const list = document.getElementById("reportList");
                if (!reports || reports.length === 0) {
                    list.innerHTML = `<p class="text-xs text-slate-400 text-center py-3">No reports uploaded yet.</p>`;
                    return;
                }
                list.innerHTML = reports.map((r) => `
                    <div class="flex items-center justify-between bg-slate-50 border border-slate-100 rounded-xl p-3">
                        <div>
                            <span class="font-bold text-sm text-slate-700">${escapeHtml(r.category)}</span>
                            <span class="text-xs text-slate-400 ml-2">${escapeHtml(r.month)} ${escapeHtml(r.year)}</span>
                            <div class="text-xs text-slate-500">${escapeHtml(r.filename)}</div>
                        </div>
                        <div class="flex items-center gap-3">
                            <a href="/api/passport/reports/${r.id}/download" class="text-blue-500 hover:text-blue-700 text-xs"><i class="fa-solid fa-download"></i></a>
                            <button onclick="deleteReport(${r.id})" class="text-red-400 hover:text-red-600 text-xs"><i class="fa-solid fa-trash"></i></button>
                        </div>
                    </div>`).join("");
            });
    }

    reportForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const fileInput = document.getElementById("reportFile");
        if (!fileInput.files.length) return;

        const formData = new FormData();
        formData.append("file", fileInput.files[0]);
        formData.append("category", document.getElementById("reportCategory").value);
        formData.append("month", document.getElementById("reportMonth").value);
        formData.append("year", document.getElementById("reportYear").value);

        const submitBtn = reportForm.querySelector("button[type='submit']");
        submitBtn.disabled = true;
        submitBtn.textContent = "Uploading...";

        try {
            await fetch("/api/passport/reports", { method: "POST", body: formData });
            reportForm.reset();
            loadReports();
        } finally {
            submitBtn.disabled = false;
            submitBtn.textContent = "Upload Report";
        }
    });

    window.deleteReport = async (id) => {
        await fetch(`/api/passport/reports/${id}`, { method: "DELETE" });
        loadReports();
    };

    loadReports();
}

// ---------- Home page: Personalized Snapshot ----------

const passportSnapshotCard = document.getElementById("passportSnapshotCard");
if (passportSnapshotCard) {
    fetch("/api/passport")
        .then((res) => res.json())
        .then((data) => {
            const emptyState = document.getElementById("passportSnapshotEmpty");
            const snapshotCard = document.getElementById("passportSnapshotCard");
            const qrCard = document.getElementById("passportSnapshotQr");

            if (!data || !data.full_name) {
                emptyState.classList.remove("hidden");
                return;
            }

            document.getElementById("snapName").textContent = data.full_name || "--";
            document.getElementById("snapBlood").textContent = data.blood_group || "--";
            document.getElementById("snapAllergies").textContent = data.allergies || "None listed";
            document.getElementById("snapMeds").textContent = data.current_medicines || "None listed";

            const snapQrContainer = document.getElementById("snapQrContainer");
            snapQrContainer.innerHTML = `<img src="/api/passport/qr?t=${Date.now()}" alt="Emergency QR" class="w-28 h-28 object-contain" />`;

            snapshotCard.classList.remove("hidden");
            qrCard.classList.remove("hidden");
        })
        .catch(() => {
            document.getElementById("passportSnapshotEmpty").classList.remove("hidden");
        });
}

// ---------- Home page: Trending Misinformation ----------

const trendingContainer = document.getElementById("trendingContainer");
if (trendingContainer) {
    fetch("/api/trending?limit=5")
        .then((res) => res.json())
        .then((trending) => {
            if (!trending || trending.length === 0) {
                trendingContainer.innerHTML = `<div class="text-center text-slate-400 text-sm py-6">No trends yet -- check a few claims to build history.</div>`;
                return;
            }

            trendingContainer.innerHTML = trending.map((t) => {
                const colors = verdictColorClasses(t.verdict);
                return `
                    <div class="bg-white p-4 rounded-xl border ${colors.badge} flex items-center justify-between gap-4">
                        <div class="flex items-center gap-3 min-w-0">
                            <span class="text-[10px] font-black uppercase px-2 py-1 rounded-full ${colors.badge} shrink-0">${escapeHtml(t.verdict || "Unverified")}</span>
                            <p class="text-sm font-semibold text-slate-700 truncate">"${escapeHtml(t.claim_text || "")}"</p>
                        </div>
                        <span class="text-xs font-bold text-slate-400 shrink-0">${escapeHtml(t.check_count)}x checked</span>
                    </div>`;
            }).join("");
        })
        .catch(() => {
            trendingContainer.innerHTML = `<div class="text-center text-red-400 text-sm py-6">Couldn't load trending data.</div>`;
        });
}

// ---------- Home page: Latest Health Alerts (live from history) ----------

const latestAlertsContainer = document.getElementById("latestAlertsContainer");
if (latestAlertsContainer) {
    fetch("/api/history?limit=3")
        .then((res) => res.json())
        .then((history) => {
            if (!history || history.length === 0) {
                latestAlertsContainer.innerHTML = `
                    <div class="md:col-span-3 text-center text-slate-400 text-sm py-6">
                        No claims checked yet. <a href="/checker" class="text-blue-600 font-bold hover:underline">Check your first claim &rarr;</a>
                    </div>`;
                return;
            }

            latestAlertsContainer.innerHTML = history.map((h) => {
                const colors = verdictColorClasses(h.verdict);
                return `
                    <div class="bg-white p-5 border rounded-2xl shadow-sm ${colors.badge}">
                        <span class="text-xs font-black uppercase tracking-wide">${escapeHtml(h.verdict || "Unverified")}</span>
                        <p class="text-sm font-bold text-slate-800 mt-2 leading-snug">"${escapeHtml((h.claim_text || "").slice(0, 90))}${(h.claim_text || "").length > 90 ? "..." : ""}"</p>
                        <p class="text-xs text-slate-400 mt-2">${escapeHtml(h.timestamp || "")}</p>
                    </div>`;
            }).join("");
        })
        .catch(() => {
            latestAlertsContainer.innerHTML = `<div class="md:col-span-3 text-center text-red-400 text-sm py-6">Couldn't load recent alerts.</div>`;
        });
}

function escapeHtml(str) {
    if (str === null || str === undefined) return "";
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}