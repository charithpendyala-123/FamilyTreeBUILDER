// State Management
let auth = null; // Holds login session data: { tree_id, tree_name, contributor_id, contributor_name, contributor_email }
let selectedPersonId = null; // Currently selected person primary key ID
let activeAction = null; // Currently showing form action name
let network = null; // Vis.js Network instance\
let currentPersonUpdatedAt = null; // Concurrency checking timestamp
let collapsedNodeIds = new Set();  // Collapsed branch trackers


// Photo cache & helper utilities for Canvas rendering
let base64ImageCache = {}; 

async function getBase64Image(url) {
    try {
        const res = await fetch(url);
        if (!res.ok) return null;
        const blob = await res.blob();
        return new Promise((resolve) => {
            const reader = new FileReader();
            reader.onloadend = () => resolve(reader.result);
            reader.onerror = () => resolve(null);
            reader.readAsDataURL(blob);
        });
    } catch (err) {
        return null;
    }
}

async function preloadNodePhotos(persons) {
    for (const p of persons) {
        if (p.photo_path && !base64ImageCache[p.id]) {
            const filename = p.photo_path.replace(/\\/g, '/').split('/').pop();
            const url = window.location.origin + "/media/" + filename;
            const base64Data = await getBase64Image(url);
            if (base64Data) {
                base64ImageCache[p.id] = base64Data;
                // Dynamically update the node in Vis.js DataSet to trigger redraw
                if (network) {
                    const updatedCard = createSvgNodeCard(p, p.id === selectedPersonId);
                    network.body.data.nodes.update({ id: p.id, image: updatedCard });
                }
            }
        }
    }
}
// Dynamic SVG Node Card Generator
// Dynamic SVG Node Card Generator
function createSvgNodeCard(person, isSelected) {
    const borderCol = isSelected ? "#ffaa00" : (person.gender === "Male" ? "#1b6dc1" : (person.gender === "Female" ? "#c05c6e" : "#5f6368"));
    const bgCol = isSelected ? "#fffbeb" : "#ffffff";
    const headerBgCol = person.gender === "Male" ? "#1b6dc1" : (person.gender === "Female" ? "#c05c6e" : "#5f6368");
    
    // Check if the base64 data URI is preloaded in cache, otherwise fallback to silhouette
    let imgUri = "";
    if (person.photo_path && base64ImageCache[person.id]) {
        imgUri = base64ImageCache[person.id];
    } else {
        const svg = person.gender === "Male" ? MALE_SVG : (person.gender === "Female" ? FEMALE_SVG : UNKNOWN_SVG);
        imgUri = "data:image/svg+xml;utf8," + encodeURIComponent(svg);
    }

    const name = `${person.first_name} ${person.surname_now || ""}`.trim();
    const phone = person.phone || "-";
    const email = person.email || "-";
    const dob = formatDisplayDate(person.birth_date);
    const dod = person.deceased === 1 ? formatDisplayDate(person.death_date) : "";
    const dates = dod ? `${dob} - ${dod}` : `${dob}`;
    
    // Truncate notes if they are too long to fit the card width
    const rawNotes = person.biography || "";
    let displayNotes = rawNotes.trim();
    if (displayNotes.length > 25) {
        displayNotes = displayNotes.substring(0, 22) + "...";
    }
    
    const escapeXml = (unsafe) => {
        if (!unsafe) return "";
        return unsafe.replace(/[<>&'"]/g, function (c) {
            switch (c) {
                case '<': return '&lt;';
                case '>': return '&gt;';
                case '&': return '&amp;';
                case '\'': return '&apos;';
                case '"': return '&quot;';
                default: return c;
            }
        });
    };

    const escName = escapeXml(name);
    const escPhone = escapeXml(phone);
    const escEmail = escapeXml(email);
    const escDates = escapeXml(dates);
    const escNotes = escapeXml(displayNotes || "-");

    const svgString = `
    <svg xmlns="http://www.w3.org/2000/svg" width="200" height="170" viewBox="0 0 200 170">
      <defs>
        <clipPath id="circleClip_${person.id}">
          <circle cx="35" cy="55" r="25" />
        </clipPath>
      </defs>
      <rect x="2" y="2" width="196" height="166" rx="8" ry="8" fill="${bgCol}" stroke="${borderCol}" stroke-width="4"/>
      <rect x="2" y="2" width="196" height="10" rx="4" ry="4" fill="${headerBgCol}"/>
      <circle cx="35" cy="55" r="27" fill="none" stroke="${borderCol}" stroke-width="2"/>
      <image x="10" y="30" width="50" height="50" href="${imgUri}" clip-path="url(#circleClip_${person.id})"/>
      <text x="70" y="45" font-family="system-ui, -apple-system, sans-serif" font-size="12" font-weight="bold" fill="#2c3e50">${escName}</text>
      <text x="70" y="60" font-family="system-ui, -apple-system, sans-serif" font-size="9" fill="#7f8c8d">${escDates}</text>
      <line x1="10" y1="90" x2="190" y2="90" stroke="#eee" stroke-width="1"/>
      <text x="15" y="110" font-family="system-ui, -apple-system, sans-serif" font-size="9" fill="#7f8c8d">✉ ${escEmail}</text>
      <text x="15" y="130" font-family="system-ui, -apple-system, sans-serif" font-size="9" fill="#7f8c8d">📞 ${escPhone}</text>
      <line x1="10" y1="142" x2="190" y2="142" stroke="#eee" stroke-width="1"/>
      <text x="15" y="156" font-family="system-ui, -apple-system, sans-serif" font-size="9" fill="#7f8c8d">📝 ${escNotes}</text>
    </svg>
    `;

    return "data:image/svg+xml;utf8," + encodeURIComponent(svgString);
}
// Date format helpers
function dbDateToInputDate(dbDate) {
    if (!dbDate) return "";
    if (dbDate.includes("/")) {
        // Converts DD/MM/YYYY (SQLite text) -> YYYY-MM-DD (needed for HTML date input values)
        const parts = dbDate.split("/");
        if (parts.length === 3) {
            const day = parts[0].padStart(2, '0');
            const month = parts[1].padStart(2, '0');
            const year = parts[2];
            return `${year}-${month}-${day}`;
        }
    }
    return dbDate; // If it's already in YYYY-MM-DD format
}

function formatDisplayDate(dateStr) {
    if (!dateStr) return "Unknown";
    if (dateStr.includes("-")) {
        // Converts YYYY-MM-DD -> DD/MM/YYYY for friendly visual labels
        const parts = dateStr.split("-");
        if (parts.length === 3) {
            return `${parts[2]}/${parts[1]}/${parts[0]}`;
        }
    }
    return dateStr;
}

// Default silhouette SVGs for visual fallbacks
const MALE_SVG = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="120" height="120"><circle cx="50" cy="50" r="50" fill="#e6f0fa"/><circle cx="50" cy="35" r="18" fill="#1b6dc1"/><path d="M50,56 C30,56 20,70 20,85 L80,85 C80,70 70,56 50,56 Z" fill="#1b6dc1"/></svg>`;
const FEMALE_SVG = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="120" height="120"><circle cx="50" cy="50" r="50" fill="#fceef0"/><circle cx="50" cy="35" r="18" fill="#c05c6e"/><path d="M50,56 C32,56 22,70 22,85 L78,85 C78,70 68,56 50,56 Z" fill="#c05c6e"/><path d="M50,20 C42,20 38,28 38,36 C38,40 40,44 42,46 C44,48 45,52 46,55 L54,55 C55,52 56,48 58,46 C60,44 62,40 62,36 C62,28 58,20 50,20 Z" fill="#c05c6e"/></svg>`;
const UNKNOWN_SVG = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="120" height="120"><circle cx="50" cy="50" r="50" fill="#f0f2f5"/><circle cx="50" cy="35" r="18" fill="#5f6368"/><path d="M50,56 C30,56 20,70 20,85 L80,85 C80,70 70,56 50,56 Z" fill="#5f6368"/></svg>`;

// Load session from localStorage on startup
function init() {
    const savedAuth = localStorage.getItem("auth");
    if (savedAuth) {
        auth = JSON.parse(savedAuth);
        showPage("dashboard");
    } else {
        showPage("landing");
    }
    setupEventListeners();
}

// Global page routing
// Global page routing
function showPage(pageId) {
    // Hide all sections
    document.querySelectorAll(".page-section").forEach(s => s.style.display = "none");
    document.getElementById("nav-dropdown-container").style.display = "none";
 
    // Show dropdown and set email header on any page except the landing page
    if (pageId !== "landing" && auth) {
        document.getElementById("nav-dropdown-container").style.display = "block";
        document.getElementById("user-email-display").textContent = auth.contributor_email;
     }
 
        // Update active navigation indicator in the header dropdown
    document.querySelectorAll(".dropdown-item").forEach(item => {
        const val = item.getAttribute("data-value");
        const indicator = item.querySelector(".current-indicator");
        if (indicator) {
            indicator.style.display = (val === pageId) ? "inline-block" : "none";
        }
    });

    if (pageId === "landing") {
        document.getElementById("page-landing").style.display = "block";
        showLandingChoice();
    } else if (pageId === "dashboard") {
        document.getElementById("page-dashboard").style.display = "block";
        loadDashboard();
    } else if (pageId === "my_trees") {
        document.getElementById("page-my-trees").style.display = "block";
        loadMyTrees();
    } else if (pageId === "settings") {
        document.getElementById("page-settings").style.display = "block";
        loadSettings();
    }
}

// Landing View Toggle
function showLandingChoice() {
    document.getElementById("landing-choice-view").style.display = "block";
    document.getElementById("landing-create-view").style.display = "none";
    document.getElementById("landing-enter-view").style.display = "none";
}

// Notifications helper
function showFeedback(message, type = "success") {
    const container = document.getElementById("feedback-container");
    container.innerHTML = `<div class="feedback-banner ${type}">${message}</div>`;
    setTimeout(() => { container.innerHTML = ""; }, 5000);
}

// Setup Event Listeners
function setupEventListeners() {
    // Landing navigation choice
    document.getElementById("btn-show-create").addEventListener("click", () => {
        document.getElementById("landing-choice-view").style.display = "none";
        document.getElementById("landing-create-view").style.display = "block";
    });
    document.getElementById("btn-show-enter").addEventListener("click", () => {
        document.getElementById("landing-choice-view").style.display = "none";
        document.getElementById("landing-enter-view").style.display = "block";
    });
    document.getElementById("btn-back-create").addEventListener("click", showLandingChoice);
    document.getElementById("btn-back-enter").addEventListener("click", showLandingChoice);

    // Form Submissions
    document.getElementById("create-tree-form").addEventListener("submit", handleCreateTree);
    document.getElementById("enter-tree-form").addEventListener("submit", handleEnterTree);
    document.getElementById("first-member-form").addEventListener("submit", handleAddFirstMember);
    document.getElementById("edit-personal-form").addEventListener("submit", handleSavePersonal);
    document.getElementById("edit-bio-form").addEventListener("submit", handleSaveBio);
    document.getElementById("edit-image-form").addEventListener("submit", handleUploadImage);

    // Cancel Forms edit button listeners
    document.getElementById("btn-cancel-personal").addEventListener("click", () => toggleEditState("personal", false));
    document.getElementById("btn-cancel-bio").addEventListener("click", () => toggleEditState("biography", false));
    document.getElementById("btn-cancel-image").addEventListener("click", () => toggleEditState("image", false));
    document.getElementById("btn-delete-image").addEventListener("click", handleDeleteImage);

    // Nav Bar Dropdown Selection
        // Custom Nav Bar Dropdown Selection
    const dropdown = document.getElementById("header-custom-dropdown");
    const trigger = document.getElementById("dropdown-email-trigger");

    trigger.addEventListener("click", (e) => {
        e.stopPropagation();
        dropdown.classList.toggle("open");
    });

    // Close the dropdown when clicking anywhere else on the document
    document.addEventListener("click", () => {
        dropdown.classList.remove("open");
    });

    // Handle dropdown item selections
    document.querySelectorAll(".dropdown-item").forEach(item => {
        item.addEventListener("click", (e) => {
            const val = e.currentTarget.getAttribute("data-value");
            dropdown.classList.remove("open");
            
            if (val === "logout") {
                auth = null;
                localStorage.removeItem("auth");
                selectedPersonId = null;
                showPage("landing");
            } else if (val === "my_trees") {
                showPage("my_trees");
            } else if (val === "settings") {
                showPage("settings");
            } else if (val === "dashboard") {
                showPage("dashboard");
            }
        });
    });

    // Sub-page Back buttons
    document.getElementById("btn-mytrees-back").addEventListener("click", () => showPage("dashboard"));
    document.getElementById("btn-settings-back").addEventListener("click", () => showPage("dashboard"));

    // Global dialog warnings
    document.getElementById("btn-warning-ok").addEventListener("click", () => {
        document.getElementById("modal-warning").style.display = "none";
    });

    // Search bar keyup
    

    // Canvas Toolbar buttons
    document.getElementById("tb-zoom-in").addEventListener("click", () => network && network.moveTo({ scale: network.getScale() * 1.2 }));
    document.getElementById("tb-zoom-out").addEventListener("click", () => network && network.moveTo({ scale: network.getScale() * 0.8 }));
    document.getElementById("tb-fit").addEventListener("click", () => network && network.fit());
    document.getElementById("tb-refresh").addEventListener("click", () => {
        if (auth && auth.tree_id) {
            // Clear all manually saved node coordinates for this tree
            Object.keys(localStorage).forEach(key => {
                if (key.startsWith(`pos_${auth.tree_id}_`)) {
                    localStorage.removeItem(key);
                }
            });
        }
        network = null; // Clear coordinates cache to reset manual layout
        loadDashboard();
    });
    document.getElementById("tb-export").addEventListener("click", triggerJSONExport);
    document.getElementById("tb-undo").addEventListener("click", handleUndoClick);
    document.getElementById("tb-redo").addEventListener("click", handleRedoClick);

    // Edit Details Profile button toggles
    document.querySelectorAll(".edit-person-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            const activeTab = document.querySelector(".tab-link.active").textContent.toLowerCase();
            toggleEditState(activeTab, true);
        });
    });

    // Relationship Action popups triggers
    document.getElementById("action-btn-parents").addEventListener("click", () => showActionForm("add_parents"));
    document.getElementById("action-btn-sibling").addEventListener("click", () => showActionForm("add_sibling"));
    document.getElementById("action-btn-partner").addEventListener("click", () => showActionForm("add_partner"));
    document.getElementById("action-btn-child").addEventListener("click", () => showActionForm("add_child"));
    document.getElementById("action-btn-collapse").addEventListener("click", () => toggleBranchCollapse(selectedPersonId));
    document.getElementById("action-btn-merge").addEventListener("click", () => showActionForm("merge"));
    document.getElementById("action-btn-delete").addEventListener("click", () => showActionForm("delete"));

    // Action Form submissions
    document.querySelectorAll(".btn-action-cancel").forEach(btn => {
        btn.addEventListener("click", () => showActionForm(null));
    });
    document.getElementById("form-action-parents").addEventListener("submit", handleAddParentsAction);
    document.getElementById("form-action-sibling").addEventListener("submit", handleAddSiblingAction);
    document.getElementById("form-action-partner").addEventListener("submit", handleAddPartnerAction);
    document.getElementById("form-action-child").addEventListener("submit", handleAddChildAction);
    document.getElementById("form-action-merge").addEventListener("submit", handleMergeSubmit);
    document.getElementById("btn-confirm-delete").addEventListener("click", handleDeleteConfirmAction);

    // Modal Audit history triggers
    document.getElementById("btn-trigger-history-modal").addEventListener("click", openHistoryModal);
    document.getElementById("btn-close-history-modal").addEventListener("click", () => {
        document.getElementById("modal-history").style.display = "none";
    });

    // Tree settings modification
    document.getElementById("settings-details-form").addEventListener("submit", handleUpdateTreeSettings);
    document.getElementById("btn-export-tree").addEventListener("click", triggerJSONExport);
    document.getElementById("btn-import-tree").addEventListener("click", handleImportTree);

    // Deceased toggle show Date of Death input field
    document.getElementById("p-edit-deceased").addEventListener("change", (e) => {
        document.getElementById("p-edit-dod-group").style.display = e.target.checked ? "block" : "none";
    });
}

// Tab Switching
function switchTab(evt, tabId) {
    document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
    document.querySelectorAll(".tab-link").forEach(l => l.classList.remove("active"));
    document.getElementById(tabId).classList.add("active");
    evt.currentTarget.classList.add("active");
}

// Toggle Edit View Panels
function toggleEditState(tabName, isEdit) {
    if (tabName === "personal") {
        document.getElementById("personal-read-state").style.display = isEdit ? "none" : "block";
        document.getElementById("personal-edit-state").style.display = isEdit ? "block" : "none";
        if (isEdit) populatePersonalEditForm();
    } else if (tabName === "biography") {
        document.getElementById("biography-read-state").style.display = isEdit ? "none" : "block";
        document.getElementById("biography-edit-state").style.display = isEdit ? "block" : "none";
        if (isEdit) populateBioEditForm();
    } else if (tabName === "image") {
        document.getElementById("image-read-state").style.display = isEdit ? "none" : "block";
        document.getElementById("image-edit-state").style.display = isEdit ? "block" : "none";
    }
}

// ----------------- API OPERATIONS -----------------

async function handleCreateTree(e) {
    e.preventDefault();
    const tree_name = document.getElementById("create-tree-name").value;
    const password = document.getElementById("create-tree-pw").value;
    const creator_name = document.getElementById("create-creator-name").value;
    const creator_email = document.getElementById("create-creator-email").value;

    try {
        const res = await fetch("/api/trees/create", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ tree_name, password, creator_name, creator_email })
        });
        if (!res.ok) throw new Error(await res.text());
        auth = await res.json();
        localStorage.setItem("auth", JSON.stringify(auth));
        selectedPersonId = auth.selected_person_id;
        showFeedback("Family Tree created successfully!");
        showPage("dashboard");
    } catch (err) {
        showFeedback(err.message || "Failed to create tree.", "error");
    }
}

async function handleEnterTree(e) {
    e.preventDefault();
    const tree_name = document.getElementById("enter-tree-name").value;
    const password = document.getElementById("enter-tree-pw").value;
    const contributor_name = document.getElementById("enter-contributor-name").value;
    const contributor_email = document.getElementById("enter-contributor-email").value;

    try {
        const res = await fetch("/api/trees/enter", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ tree_name, password, contributor_name, contributor_email })
        });
        if (!res.ok) throw new Error(await res.text());
        auth = await res.json();
        localStorage.setItem("auth", JSON.stringify(auth));
        showFeedback(auth.message);
        showPage("dashboard");
    } catch (err) {
        showFeedback("Invalid Tree Name or Password.", "error");
    }
}

async function loadMyTrees() {
    try {
        const res = await fetch(`/api/trees/my-trees?email=${auth.contributor_email}`);
        const trees = await res.json();
        const container = document.getElementById("my-trees-list");
        container.innerHTML = "";
        
        trees.forEach(t => {
            const card = document.createElement("div");
            card.className = "landing-card";
            card.style.marginBottom = "15px";
            card.innerHTML = `
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <div>
                        <h4>🌳 ${t.tree_name}</h4>
                        <small>Members: ${t.member_count} | Created: ${t.created_at.substring(0, 10)}</small>
                    </div>
                    <button class="back-btn" onclick="enterSpecificTree(${t.id}, '${t.tree_name}')">Enter Tree</button>
                </div>
            `;
            container.appendChild(card);
        });
    } catch (err) {
        showFeedback("Failed to load joined trees.", "error");
    }
}

function enterSpecificTree(treeId, treeName) {
    auth.tree_id = treeId;
    auth.tree_name = treeName;
    localStorage.setItem("auth", JSON.stringify(auth));
    selectedPersonId = null;
    showPage("dashboard");
}

async function loadSettings() {
    document.getElementById("settings-tree-name").value = auth.tree_name;
    document.getElementById("settings-tree-pw").value = "";
    
    // Load Stats
    try {
        const res = await fetch(`/api/trees/${auth.tree_id}/stats`);
        const stats = await res.json();
        
        // Select active Tree Type setting
        if (stats.tree_type === "mythology") {
            document.getElementById("tree-type-mythology").checked = true;
        } else {
            document.getElementById("tree-type-family").checked = true;
        }

        const container = document.getElementById("settings-stats-view");
        container.innerHTML = `
            <h3>Display Statistics</h3>
            <div class="stat-item">
                <div class="stat-val">${stats.members}</div>
                <div class="stat-lbl">Total Members</div>
            </div>
            <div class="stat-item">
                <div class="stat-val">${stats.contributors}</div>
                <div class="stat-lbl">Total Contributors</div>
            </div>
            <div class="stat-item">
                <div class="stat-val">${stats.relationships}</div>
                <div class="stat-lbl">Total Relationships</div>
            </div>
            <p><strong>Last Updated:</strong> ${stats.last_updated.substring(0, 19).replace('T', ' ')}</p>
        `;
    } catch (err) {
        showFeedback("Failed to load statistics.", "error");
    }
}

async function handleUpdateTreeSettings(e) {
    e.preventDefault();
    const new_name = document.getElementById("settings-tree-name").value;
    const new_password = document.getElementById("settings-tree-pw").value;
    const tree_type = document.querySelector('input[name="settings-tree-type"]:checked').value;

    try {
        const res = await fetch(`/api/trees/${auth.tree_id}/settings`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                new_name,
                new_password: new_password || null,
                contributor_id: auth.contributor_id,
                tree_type
            })
        });
        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.detail || "Failed to update settings.");
        }
        auth.tree_name = new_name;
        localStorage.setItem("auth", JSON.stringify(auth));
        showFeedback("Tree settings updated!");
        loadSettings();
    } catch (err) {
        showFeedback(err.message || "Failed to update settings.", "error");
    }
}

// ----------------- DASHBOARD WORKSPACE OPERATIONS -----------------

async function loadDashboard() {
    showActionForm(null);
    toggleEditState("personal", false);
    toggleEditState("biography", false);
    toggleEditState("image", false);
    
    await loadDashboardGraph();
    await loadProfileDetails();
    await loadActivityLogs();
    await updateUndoRedoStatus();
}

async function loadDashboardGraph(searchQuery = "") {
    try {
        const url = `/api/trees/${auth.tree_id}/persons` + (searchQuery ? `?search=${encodeURIComponent(searchQuery)}` : "");
        const res = await fetch(url);
        const persons = await res.json();

        const relRes = await fetch(`/api/trees/${auth.tree_id}/relationships`);
        const relationships = await relRes.json();

        if (persons.length === 0) {
            document.getElementById("empty-panel-view").style.display = "block";
            document.getElementById("profile-panel-view").style.display = "none";
            document.getElementById("tree-canvas-container").innerHTML = "<div style='padding:20px;'>No members present yet.</div>";
            return;
        }

        document.getElementById("empty-panel-view").style.display = "none";
        document.getElementById("profile-panel-view").style.display = "block";

        if (!selectedPersonId || !persons.some(p => p.id === selectedPersonId)) {
            selectedPersonId = persons[0].id;
            loadProfileDetails();
        }

        renderVisGraph(persons, relationships);
        preloadNodePhotos(persons); // Load photos in background to update node cards
    } catch (err) {
        showFeedback("Error loading family tree canvas.", "error");
    }
}

function renderVisGraph(persons, relationships) {
    const nodesArray = [];
    const edgesArray = [];

    // Retrieve current coordinates from existing network to preserve manual drag adjustments
    const currentPositions = network ? network.getPositions() : {};

    // 0. Compute hidden descendant nodes due to branching collapse
    const parentToChildren = {};
    relationships.forEach(r => {
        if (r.relationship_type === "parent-child") {
            const p = r.person1_id;
            const c = r.person2_id;
            if (!parentToChildren[p]) {
                parentToChildren[p] = [];
            }
            parentToChildren[p].push(c);
        }
    });

    const hiddenNodeIds = new Set();
    collapsedNodeIds.forEach(parentId => {
        const queue = [...(parentToChildren[parentId] || [])];
        while (queue.length > 0) {
            const curr = queue.shift();
            if (!hiddenNodeIds.has(curr)) {
                hiddenNodeIds.add(curr);
                const children = parentToChildren[curr] || [];
                queue.push(...children);
            }
        }
    });

    // 1. Build adjacency list for generational level calculation
    const adj = {};
    persons.forEach(p => {
        adj[p.id] = [];
    });

    relationships.forEach(r => {
        const p1 = r.person1_id;
        const p2 = r.person2_id;
        if (adj[p1] !== undefined && adj[p2] !== undefined) {
            if (r.relationship_type === "parent-child") {
                adj[p1].push({ to: p2, type: "parent-child", isChild: true });
                adj[p2].push({ to: p1, type: "parent-child", isChild: false });
            } else if (r.relationship_type === "partner") {
                adj[p1].push({ to: p2, type: "partner" });
                adj[p2].push({ to: p1, type: "partner" });
            } else if (r.relationship_type === "sibling") {
                adj[p1].push({ to: p2, type: "sibling" });
                adj[p2].push({ to: p1, type: "sibling" });
            }
        }
    });

    // 2. BFS traversal to compute levels relative to the root
    const levels = {};
    const visited = new Set();

    persons.forEach(p => {
        if (!visited.has(p.id)) {
            const queue = [{ id: p.id, level: 0 }];
            visited.add(p.id);
            levels[p.id] = 0;

            while (queue.length > 0) {
                const curr = queue.shift();
                const neighbors = adj[curr.id] || [];
                neighbors.forEach(n => {
                    if (!visited.has(n.to)) {
                        let nextLevel = curr.level;
                        if (n.type === "parent-child") {
                            nextLevel = curr.level + (n.isChild ? 1 : -1);
                        } else {
                            nextLevel = curr.level;
                        }
                        levels[n.to] = nextLevel;
                        visited.add(n.to);
                        queue.push({ id: n.to, level: nextLevel });
                    }
                });
            }
        }
    });

    // 3. Shift levels so the minimum level starts at 0
    let minLevel = Infinity;
    Object.values(levels).forEach(lvl => {
        if (lvl < minLevel) minLevel = lvl;
    });

    if (minLevel !== Infinity) {
        persons.forEach(p => {
            if (levels[p.id] !== undefined) {
                levels[p.id] = levels[p.id] - minLevel;
            } else {
                levels[p.id] = 0;
            }
        });
    }

    // 4. Calculate initial generation positioning grid
    const personsByLevel = {};
    persons.forEach(p => {
        const lvl = levels[p.id] || 0;
        if (!personsByLevel[lvl]) personsByLevel[lvl] = [];
        personsByLevel[lvl].push(p.id);
    });

    const xCoords = {};
    const yCoords = {};
    const levelSeparation = 200; // Vertical spacing between generations
    const nodeSpacing = 280;     // Horizontal spacing between cards

    Object.keys(personsByLevel).forEach(lvl => {
        const levelNum = parseInt(lvl);
        const pids = personsByLevel[lvl];
        const count = pids.length;
        pids.forEach((pid, idx) => {
            const savedPos = localStorage.getItem(`pos_${auth.tree_id}_${pid}`);
            if (savedPos) {
                const pos = JSON.parse(savedPos);
                xCoords[pid] = pos.x;
                yCoords[pid] = pos.y;
            } else if (currentPositions[pid] && currentPositions[pid].x !== undefined) {
                // If the user already dragged it, preserve its position
                xCoords[pid] = currentPositions[pid].x;
                yCoords[pid] = currentPositions[pid].y;
            } else {
                // Otherwise, assign a structured grid location
                xCoords[pid] = (idx - (count - 1) / 2) * nodeSpacing;
                yCoords[pid] = levelNum * levelSeparation;
            }
        });
    });

    // Map Persons to Vis.js nodes using the SVG Card
    persons.forEach(p => {
        const isSelected = p.id === selectedPersonId;
        const cardUrl = createSvgNodeCard(p, isSelected);

        nodesArray.push({
            id: p.id,
            label: "", // Label is rendered inside the SVG itself
            shape: "image",
            image: cardUrl,
            size: 70, // Rendered size of the card box
            x: xCoords[p.id],
            y: yCoords[p.id],
            hidden: hiddenNodeIds.has(p.id)
        });
    });

    // Map Relationships to Vis.js edges
    relationships.forEach(r => {
        const isEdgeHidden = hiddenNodeIds.has(r.person1_id) || hiddenNodeIds.has(r.person2_id);
        if (r.relationship_type === "parent-child") {
            const isAdoptive = r.relationship_subtype === "adoptive";
            const edgeColor = isAdoptive ? "#27ae60" : "#1b6dc1";
            edgesArray.push({
                from: r.person1_id,
                to: r.person2_id,
                arrows: "to",
                color: { color: edgeColor, highlight: edgeColor },
                width: 2,
                dashes: isAdoptive,
                hidden: isEdgeHidden
            });
        } else if (r.relationship_type === "partner") {
            let edgeColor = "#c05c6e";
            if (r.relationship_status === "divorced") {
                edgeColor = "#7f8c8d";
            } else if (r.relationship_status === "widowed") {
                edgeColor = "#333333";
            }
            edgesArray.push({
                from: r.person1_id,
                to: r.person2_id,
                color: { color: edgeColor, highlight: edgeColor },
                width: 2,
                dashes: true,
                arrows: "",
                hidden: isEdgeHidden
            });
        } else if (r.relationship_type === "sibling") {
            edgesArray.push({
                from: r.person1_id,
                to: r.person2_id,
                color: { color: "#7f8c8d", highlight: "#7f8c8d" },
                width: 2,
                dashes: true,
                arrows: "",
                hidden: isEdgeHidden
            });
        }
    });

    const container = document.getElementById("tree-canvas-container");
    const data = { nodes: new vis.DataSet(nodesArray), edges: new vis.DataSet(edgesArray) };
    const options = {
        layout: {
            hierarchical: {
                enabled: false // Disable hierarchical layout to unlock vertical dragging
            }
        },
        physics: { enabled: false }, // Keep physics off so dragged nodes don't float away
        interaction: {
            dragNodes: true // Ensure card dragging is enabled
        }
    };

    network = new vis.Network(container, data, options);

    network.on("selectNode", (params) => {
        if (params.nodes.length > 0) {
            selectedPersonId = parseInt(params.nodes[0]);
            loadDashboard();
        }
    });

    network.on("dragEnd", (params) => {
        if (params.nodes.length > 0) {
            params.nodes.forEach(nodeId => {
                const pid = parseInt(nodeId);
                const pos = network.getPositions([pid])[pid];
                if (pos && auth && auth.tree_id) {
                    localStorage.setItem(`pos_${auth.tree_id}_${pid}`, JSON.stringify(pos));
                }
            });
        }
    });
}

async function loadProfileDetails() {
    if (!selectedPersonId) return;

    try {
        const res = await fetch(`/api/persons/${selectedPersonId}`);
        if (!res.ok) throw new Error();
        const p = await res.json();
        currentPersonUpdatedAt = p.updated_at;

        // 1. Title Name
        document.getElementById("profile-header-name").textContent = `👤 ${p.first_name} ${p.surname_now || ""}`.trim();

        // Update Collapse Branch button text based on current state
        const collapseBtn = document.getElementById("action-btn-collapse");
        if (collapseBtn) {
            collapseBtn.textContent = collapsedNodeIds.has(selectedPersonId) ? "EXPAND BRANCH" : "COLLAPSE BRANCH";
        }

        // 2. Personal Tab Read fields
        document.getElementById("p-read-fname").textContent = p.first_name;
        document.getElementById("p-read-sname").textContent = p.surname_now || "-";
        document.getElementById("p-read-sbirth").textContent = p.surname_at_birth || "-";
        document.getElementById("p-read-gender").textContent = p.gender || "-";
        document.getElementById("p-read-dob").textContent = formatDisplayDate(p.birth_date);

        if (p.deceased === 1) {
            document.getElementById("p-read-deceased-block").style.display = "block";
            document.getElementById("p-read-dod").textContent = formatDisplayDate(p.death_date);
        } else {
            document.getElementById("p-read-deceased-block").style.display = "none";
        }

        // 3. Biography Tab Read fields (Crash-free)
        document.getElementById("b-read-profession").textContent = p.profession || "-";
        document.getElementById("b-read-phone").textContent = p.phone || "-";
        document.getElementById("b-read-email").textContent = p.email || "-";
        document.getElementById("b-read-address").textContent = p.address || "-";
        document.getElementById("b-read-biography").textContent = p.biography || "-";

        // 4. Image Tab Read fields
        const imgContainer = document.getElementById("p-read-image-container");
        const deleteImgBtn = document.getElementById("btn-delete-image"); 
        if (p.photo_url) {
            imgContainer.innerHTML = `<img src="${p.photo_url}" alt="Profile Photo">`;
            if (deleteImgBtn) deleteImgBtn.style.display = "block";
        } else {
            imgContainer.innerHTML = p.gender === "Male" ? MALE_SVG : (p.gender === "Female" ? FEMALE_SVG : UNKNOWN_SVG);
            if (deleteImgBtn) deleteImgBtn.style.display = "none";
        }
        
        loadFamilyNavigator(selectedPersonId);
    } catch (err) {
        selectedPersonId = null;
    }
}
// Populate Edit forms
async function populatePersonalEditForm() {
    const res = await fetch(`/api/persons/${selectedPersonId}`);
    const p = await res.json();
    document.getElementById("p-edit-fname").value = p.first_name;
    document.getElementById("p-edit-sname").value = p.surname_now || "";
    document.getElementById("p-edit-sbirth").value = p.surname_at_birth || "";
    document.getElementById(p.gender === "Female" ? "gen-female" : "gen-male").checked = true;
    document.getElementById("p-edit-dob").value = dbDateToInputDate(p.birth_date);

    const decCheckbox = document.getElementById("p-edit-deceased");
    decCheckbox.checked = p.deceased === 1;
    document.getElementById("p-edit-dod-group").style.display = p.deceased === 1 ? "block" : "none";
    document.getElementById("p-edit-dod").value = dbDateToInputDate(p.death_date);
}

async function populateBioEditForm() {
    const res = await fetch(`/api/persons/${selectedPersonId}`);
    const p = await res.json();
    document.getElementById("b-edit-profession").value = p.profession || "";
    document.getElementById("b-edit-phone").value = p.phone || "";
    document.getElementById("b-edit-email").value = p.email || "";
    document.getElementById("b-edit-address").value = p.address || "";
    document.getElementById("b-edit-biography").value = p.biography || "";
}

// Form submissions handlers

async function handleSavePersonal(e) {
    e.preventDefault();
    const first_name = document.getElementById("p-edit-fname").value;
    const surname_now = document.getElementById("p-edit-sname").value;
    const surname_at_birth = document.getElementById("p-edit-sbirth").value;
    const gender = document.querySelector('input[name="p-edit-gender"]:checked').value;
    const birth_date = document.getElementById("p-edit-dob").value;
    const deceased = document.getElementById("p-edit-deceased").checked ? 1 : 0;
    const death_date = document.getElementById("p-edit-dod").value;

    try {
        const res = await fetch(`/api/persons/${selectedPersonId}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                tree_id: auth.tree_id,
                contributor_id: auth.contributor_id,
                first_name, surname_now, surname_at_birth, gender, birth_date,
                deceased, death_date: deceased ? death_date : "",
                updated_at_client: currentPersonUpdatedAt
            })
        });
        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.detail || "Failed to save changes.");
        }
        showFeedback("Personal info saved!");
        loadDashboard();
    } catch (err) {
        showFeedback(err.message || "Failed to save changes.", "error");
    }
}

async function handleSaveBio(e) {
    e.preventDefault();
    const personRes = await fetch(`/api/persons/${selectedPersonId}`);
    const p = await personRes.json();

    const profession = document.getElementById("b-edit-profession").value;
    const phone = document.getElementById("b-edit-phone").value;
    const email = document.getElementById("b-edit-email").value;
    const address = document.getElementById("b-edit-address").value;
    const biography = document.getElementById("b-edit-biography").value;

    try {
        const res = await fetch(`/api/persons/${selectedPersonId}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                tree_id: auth.tree_id,
                contributor_id: auth.contributor_id,
                first_name: p.first_name,
                surname_now: p.surname_now,
                surname_at_birth: p.surname_at_birth,
                gender: p.gender,
                birth_date: p.birth_date,
                deceased: p.deceased,
                death_date: p.death_date,
                country_of_birth: p.country_of_birth || "",
                profession, 
                phone, 
                email, 
                address, 
                biography, 
                interesting_facts: p.interesting_facts || "",
                updated_at_client: currentPersonUpdatedAt
            })
        });
        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.detail || "Failed to save biography.");
        }
        showFeedback("Biography saved!");
        loadDashboard();
    } catch (err) {
        showFeedback(err.message || "Failed to save biography.", "error");
    }
}

async function handleUploadImage(e) {
    e.preventDefault();
    const fileInput = document.getElementById("p-edit-image-file");
    if (fileInput.files.length === 0) return;

    const formData = new FormData();
    formData.append("file", fileInput.files[0]);
    formData.append("tree_id", auth.tree_id);
    formData.append("contributor_id", auth.contributor_id);

    try {
        const res = await fetch(`/api/persons/${selectedPersonId}/photo`, {
            method: "POST",
            body: formData
        });
        if (!res.ok) throw new Error();
        showFeedback("Profile photo uploaded!");
        loadDashboard();
    } catch (err) {
        showFeedback("Failed to upload image.", "error");
    }
}
async function handleDeleteImage() {
    if (!confirm("Are you sure you want to delete this profile image?")) return;
    
    try {
        const res = await fetch(`/api/persons/${selectedPersonId}/photo`, {
            method: "DELETE",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                tree_id: auth.tree_id,
                contributor_id: auth.contributor_id
            })
        });
        if (!res.ok) throw new Error();
        showFeedback("Profile photo deleted successfully!");
        
        // Remove from image cache to force Vis.js canvas to redraw the silhouette
        delete base64ImageCache[selectedPersonId];
        
        loadDashboard();
    } catch (err) {
        showFeedback("Failed to delete image.", "error");
    }
}

// ----------------- RELATIONSHIPS ACTIONS forms -----------------

function toggleFormMode(formType) {
    if (formType === 'parents') {
        const mode = document.getElementById("act-parents-mode").value;
        const newFields = document.getElementById("act-parents-new-fields");
        const linkFields = document.getElementById("act-parents-link-fields");
        const linkFatherGroup = document.getElementById("act-parents-link-father-group");
        const linkMotherGroup = document.getElementById("act-parents-link-mother-group");

        if (mode === "new") {
            newFields.style.display = "block";
            linkFields.style.display = "none";
            linkFatherGroup.style.display = "none";
            linkMotherGroup.style.display = "none";
        } else if (mode === "link_father") {
            newFields.style.display = "none";
            linkFields.style.display = "block";
            linkFatherGroup.style.display = "block";
            linkMotherGroup.style.display = "none";
        } else if (mode === "link_mother") {
            newFields.style.display = "none";
            linkFields.style.display = "block";
            linkFatherGroup.style.display = "none";
            linkMotherGroup.style.display = "block";
        }
    } else if (formType === 'sibling') {
        const mode = document.getElementById("act-sibling-mode").value;
        const newFields = document.getElementById("act-sibling-new-fields");
        const linkFields = document.getElementById("act-sibling-link-fields");
        if (mode === "new") {
            newFields.style.display = "block";
            linkFields.style.display = "none";
        } else {
            newFields.style.display = "none";
            linkFields.style.display = "block";
        }
    } else if (formType === 'partner') {
        const mode = document.getElementById("act-partner-mode").value;
        const newFields = document.getElementById("act-partner-new-fields");
        const linkFields = document.getElementById("act-partner-link-fields");
        const updateFields = document.getElementById("act-partner-update-fields");
        if (mode === "new") {
            newFields.style.display = "block";
            linkFields.style.display = "none";
            updateFields.style.display = "none";
        } else if (mode === "link") {
            newFields.style.display = "none";
            linkFields.style.display = "block";
            updateFields.style.display = "none";
        } else if (mode === "update_status") {
            newFields.style.display = "none";
            linkFields.style.display = "none";
            updateFields.style.display = "block";
            loadExistingPartnerOptions();
        }
    } else if (formType === 'child') {
        const mode = document.getElementById("act-child-mode").value;
        const newFields = document.getElementById("act-child-new-fields");
        const linkFields = document.getElementById("act-child-link-fields");
        const partnerOpts = document.getElementById("act-child-partner-options-container");
        if (mode === "new") {
            newFields.style.display = "block";
            linkFields.style.display = "none";
            partnerOpts.style.display = "block";
        } else {
            newFields.style.display = "none";
            linkFields.style.display = "block";
            partnerOpts.style.display = "none";
        }
    }
}

async function populateExistingPersonsSelects() {
    try {
        const res = await fetch(`/api/trees/${auth.tree_id}/persons`);
        const persons = await res.json();
        
        // Filter out the currently selected person so they can't relate to themselves
        const candidates = persons.filter(p => p.id !== selectedPersonId);
        
        const selects = document.querySelectorAll(".existing-persons-select");
        selects.forEach(select => {
            select.innerHTML = "";
            
            // Add a default select option
            const defaultOpt = document.createElement("option");
            defaultOpt.value = "";
            defaultOpt.textContent = "-- Choose Person --";
            select.appendChild(defaultOpt);
            
            candidates.forEach(p => {
                const opt = document.createElement("option");
                opt.value = p.id;
                opt.textContent = `${p.first_name} ${p.surname_now || ""} (ID: ${p.id})`;
                select.appendChild(opt);
            });
        });
    } catch (err) {
        showFeedback("Failed to populate candidate persons lists.", "error");
    }
}

async function loadExistingPartnerOptions() {
    try {
        const res = await fetch(`/api/trees/${auth.tree_id}/relationships`);
        const relationships = await res.json();
        
        // Find partners of selected person
        const partnerIds = [];
        relationships.forEach(r => {
            if (r.relationship_type === "partner") {
                if (r.person1_id === selectedPersonId) partnerIds.push(r.person2_id);
                else if (r.person2_id === selectedPersonId) partnerIds.push(r.person1_id);
            }
        });

        const partnersList = [];
        for (const pid of partnerIds) {
            const pRes = await fetch(`/api/persons/${pid}`);
            if (pRes.ok) partnersList.push(await pRes.json());
        }

        const select = document.getElementById("act-partner-select-existing");
        if (select) {
            select.innerHTML = "";
            const defaultOpt = document.createElement("option");
            defaultOpt.value = "";
            defaultOpt.textContent = "-- Select Partner --";
            select.appendChild(defaultOpt);

            partnersList.forEach(p => {
                const opt = document.createElement("option");
                opt.value = p.id;
                opt.textContent = `${p.first_name} ${p.surname_now || ""} (ID: ${p.id})`;
                select.appendChild(opt);
            });
        }
    } catch (err) {
        showFeedback("Failed to load existing partners.", "error");
    }
}

function toggleBranchCollapse(personId) {
    if (!personId) return;
    if (collapsedNodeIds.has(personId)) {
        collapsedNodeIds.delete(personId);
        showFeedback("Branch expanded.");
    } else {
        collapsedNodeIds.add(personId);
        showFeedback("Branch collapsed.");
    }
    loadDashboard();
}

function showActionForm(actionName) {
    activeAction = actionName;
    const container = document.getElementById("active-action-form-container");
    const actionsButtons = document.getElementById("action-buttons-group");
    
    // Hide all forms first
    document.getElementById("form-action-parents").style.display = "none";
    document.getElementById("form-action-sibling").style.display = "none";
    document.getElementById("form-action-partner").style.display = "none";
    document.getElementById("form-action-child").style.display = "none";
    document.getElementById("form-action-merge").style.display = "none";
    document.getElementById("form-action-delete").style.display = "none";

    if (!actionName) {
        container.style.display = "none";
        actionsButtons.style.display = "block";
        return;
    }

    container.style.display = "block";
    actionsButtons.style.display = "none";
    document.getElementById("active-action-title").textContent = actionName.replace('_', ' ').toUpperCase();

    if (actionName === "add_parents") {
        document.getElementById("form-action-parents").style.display = "block";
        document.getElementById("act-parents-mode").value = "new";
        toggleFormMode('parents');
        populateExistingPersonsSelects();
    } else if (actionName === "add_sibling") {
        document.getElementById("form-action-sibling").style.display = "block";
        document.getElementById("act-sibling-mode").value = "new";
        toggleFormMode('sibling');
        populateExistingPersonsSelects();
    } else if (actionName === "add_partner") {
        document.getElementById("form-action-partner").style.display = "block";
        document.getElementById("act-partner-mode").value = "new";
        toggleFormMode('partner');
        populateExistingPersonsSelects();
    } else if (actionName === "add_child") {
        document.getElementById("form-action-child").style.display = "block";
        document.getElementById("act-child-mode").value = "new";
        toggleFormMode('child');
        populateExistingPersonsSelects();
        loadAddChildOptions();
    } else if (actionName === "merge") {
        document.getElementById("form-action-merge").style.display = "block";
        populateExistingPersonsSelects();
        const dupNameSpan = document.getElementById("merge-dup-name");
        if (dupNameSpan) {
            const currentName = document.getElementById("profile-header-name").textContent.replace("👤 ", "");
            dupNameSpan.textContent = `${currentName} (ID: ${selectedPersonId})`;
        }
    } else if (actionName === "delete") {
        document.getElementById("form-action-delete").style.display = "block";
        document.getElementById("delete-target-name").textContent = document.getElementById("profile-header-name").textContent.replace("👤 ", "");
    }
}

async function handleAddFirstMember(e) {
    e.preventDefault();
    const first_name = document.getElementById("first-member-fname").value;
    const surname_now = document.getElementById("first-member-sname").value;
    const gender = document.getElementById("first-member-gender").value;
    const birth_date = document.getElementById("first-member-dob").value;

    try {
        const res = await fetch("/api/persons", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ tree_id: auth.tree_id, contributor_id: auth.contributor_id, first_name, surname_now, gender, birth_date })
        });
        const out = await res.json();
        selectedPersonId = out.person_id;
        showFeedback("First member added!");
        loadDashboard();
    } catch (err) {
        showFeedback("Failed to add member.", "error");
    }
}

async function handleAddParentsAction(e) {
    e.preventDefault();
    const mode = document.getElementById("act-parents-mode").value;

    try {
        if (mode === "new") {
            const father_name = document.getElementById("act-parents-father").value;
            const mother_name = document.getElementById("act-parents-mother").value;
            if (!father_name && !mother_name) {
                throw new Error("Father or Mother name must be provided.");
            }
            const res = await fetch("/api/relationships/parents", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ tree_id: auth.tree_id, contributor_id: auth.contributor_id, child_id: selectedPersonId, father_name, mother_name })
            });
            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                throw new Error(errData.detail || "Failed to add parents.");
            }
        } else if (mode === "link_father") {
            const father_id = document.getElementById("act-parents-select-father").value;
            if (!father_id) throw new Error("Please select a father to link.");
            const res = await fetch("/api/relationships/link", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    tree_id: auth.tree_id,
                    contributor_id: auth.contributor_id,
                    person1_id: parseInt(father_id),
                    person2_id: selectedPersonId,
                    relationship_type: "parent-child",
                    relationship_subtype: "biological"
                })
            });
            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                throw new Error(errData.detail || "Failed to link father.");
            }
        } else if (mode === "link_mother") {
            const mother_id = document.getElementById("act-parents-select-mother").value;
            if (!mother_id) throw new Error("Please select a mother to link.");
            const res = await fetch("/api/relationships/link", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    tree_id: auth.tree_id,
                    contributor_id: auth.contributor_id,
                    person1_id: parseInt(mother_id),
                    person2_id: selectedPersonId,
                    relationship_type: "parent-child",
                    relationship_subtype: "biological"
                })
            });
            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                throw new Error(errData.detail || "Failed to link mother.");
            }
        }
        showFeedback("Parent(s) linked successfully!");
        loadDashboard();
    } catch (err) {
        showFeedback(err.message || "Failed to add/link parents.", "error");
    }
}

async function handleAddSiblingAction(e) {
    e.preventDefault();
    const mode = document.getElementById("act-sibling-mode").value;

    try {
        if (mode === "new") {
            const sibling_name = document.getElementById("act-sibling-name").value;
            const sibling_gender = document.getElementById("act-sibling-gender").value;
            const res = await fetch("/api/relationships/sibling", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ tree_id: auth.tree_id, contributor_id: auth.contributor_id, person_id: selectedPersonId, sibling_name, sibling_gender })
            });
            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                throw new Error(errData.detail || "Failed to add sibling.");
            }
        } else {
            const sibling_id = document.getElementById("act-sibling-select-person").value;
            if (!sibling_id) throw new Error("Please select a sibling to link.");
            const res = await fetch("/api/relationships/link", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    tree_id: auth.tree_id,
                    contributor_id: auth.contributor_id,
                    person1_id: selectedPersonId,
                    person2_id: parseInt(sibling_id),
                    relationship_type: "sibling"
                })
            });
            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                throw new Error(errData.detail || "Failed to link sibling.");
            }
        }
        showFeedback("Sibling linked successfully!");
        loadDashboard();
    } catch (err) {
        showFeedback(err.message || "Failed to add/link sibling.", "error");
    }
}

async function handleAddPartnerAction(e) {
    e.preventDefault();
    const mode = document.getElementById("act-partner-mode").value;
    const status = document.getElementById("act-partner-status").value;
    const subtype = document.getElementById("act-partner-subtype").value;

    try {
        let partner_id = null;
        if (mode === "new") {
            const partner_name = document.getElementById("act-partner-name").value;
            const partner_gender = document.getElementById("act-partner-gender").value;
            const res = await fetch("/api/relationships/partner", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ tree_id: auth.tree_id, contributor_id: auth.contributor_id, person_id: selectedPersonId, partner_name, partner_gender })
            });
            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                throw new Error(errData.detail || "Failed to add partner.");
            }
            const data = await res.json();
            partner_id = data.partner_id;
        } else if (mode === "link") {
            const select_val = document.getElementById("act-partner-select-person").value;
            if (!select_val) throw new Error("Please select a partner to link.");
            partner_id = parseInt(select_val);
            const res = await fetch("/api/relationships/link", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    tree_id: auth.tree_id,
                    contributor_id: auth.contributor_id,
                    person1_id: selectedPersonId,
                    person2_id: partner_id,
                    relationship_type: "partner",
                    relationship_status: status,
                    relationship_subtype: subtype
                })
            });
            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                throw new Error(errData.detail || "Failed to link partner.");
            }
        } else if (mode === "update_status") {
            const select_val = document.getElementById("act-partner-select-existing").value;
            if (!select_val) throw new Error("Please select a partner to update.");
            partner_id = parseInt(select_val);
        }
        
        // If updating status or setting a non-active status, update the relationship status in the database
        if (mode === "update_status" || status !== "active") {
            const statusRes = await fetch("/api/relationships/status", {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    tree_id: auth.tree_id,
                    contributor_id: auth.contributor_id,
                    person1_id: selectedPersonId,
                    person2_id: partner_id,
                    relationship_status: status
                })
            });
            if (!statusRes.ok) {
                const errData = await statusRes.json().catch(() => ({}));
                throw new Error(errData.detail || "Failed to update relationship status.");
            }
        }
        
        showFeedback(mode === "update_status" ? "Relationship status updated successfully!" : "Partner linked successfully!");
        loadDashboard();
    } catch (err) {
        showFeedback(err.message || "Failed to add/link/update partner.", "error");
    }
}

async function loadAddChildOptions() {
    try {
        // Fetch existing partners of the selected person
        const res = await fetch(`/api/trees/${auth.tree_id}/relationships`);
        const relationships = await res.json();
        
        // Find partners of selected person
        const partnerIds = [];
        relationships.forEach(r => {
            if (r.relationship_type === "partner") {
                if (r.person1_id === selectedPersonId) partnerIds.push(r.person2_id);
                else if (r.person2_id === selectedPersonId) partnerIds.push(r.person1_id);
            }
        });

        const partnersList = [];
        for (const pid of partnerIds) {
            const pRes = await fetch(`/api/persons/${pid}`);
            if (pRes.ok) partnersList.push(await pRes.json());
        }

        const container = document.getElementById("act-child-radio-group");
        container.innerHTML = "";

        // Renders Options matching screenshots
        // 1. Partnered options
        partnersList.forEach(p => {
            const div = document.createElement("div");
            div.className = "radio-option";
            div.innerHTML = `
                <input type="radio" name="child-partner-opt" value="partnered_${p.id}" id="child-opt-p-${p.id}" checked>
                <label for="child-opt-p-${p.id}">Add child with ${p.first_name} ${p.surname_now || ""}</label>
            `;
            container.appendChild(div);
        });

        // 2. New partner
        const divNew = document.createElement("div");
        divNew.className = "radio-option";
        divNew.innerHTML = `
            <input type="radio" name="child-partner-opt" value="new_partner" id="child-opt-new">
            <label for="child-opt-new">Add child with a new partner</label>
        `;
        container.appendChild(divNew);

        // 3. Single Parent
        const divSingle = document.createElement("div");
        divSingle.className = "radio-option";
        divSingle.innerHTML = `
            <input type="radio" name="child-partner-opt" value="single_parent" id="child-opt-single">
            <label for="child-opt-single">Add single parent child</label>
        `;
        container.appendChild(divSingle);

        // Add change listener to show/hide new partner fields
        document.querySelectorAll('input[name="child-partner-opt"]').forEach(radio => {
            radio.addEventListener("change", (e) => {
                document.getElementById("act-child-new-partner-fields").style.display = e.target.value === "new_partner" ? "block" : "none";
            });
        });
        
        // Trigger initial state check
        document.getElementById("act-child-new-partner-fields").style.display = "none";
    } catch (err) {
        showFeedback("Failed to load partner options.", "error");
    }
}

async function handleAddChildAction(e) {
    e.preventDefault();
    const mode = document.getElementById("act-child-mode").value;
    const subtype = document.getElementById("act-child-subtype").value;

    try {
        if (mode === "new") {
            const child_name = document.getElementById("act-child-name").value;
            const child_gender = document.getElementById("act-child-gender").value;
            const option = document.querySelector('input[name="child-partner-opt"]:checked').value;

            let parent2_id = null;

            if (option.startsWith("partnered_")) {
                parent2_id = parseInt(option.replace("partnered_", ""));
            } else if (option === "new_partner") {
                // Create partner first
                const partner_name = document.getElementById("act-child-new-partner-name").value;
                const partner_gender = document.getElementById("act-child-new-partner-gender").value;
                if (!partner_name.trim()) {
                    throw new Error("New partner name is required!");
                }
                
                const partnerRes = await fetch("/api/relationships/partner", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ tree_id: auth.tree_id, contributor_id: auth.contributor_id, person_id: selectedPersonId, partner_name, partner_gender })
                });
                if (!partnerRes.ok) {
                    const errData = await partnerRes.json().catch(() => ({}));
                    throw new Error(errData.detail || "Failed to create new partner for child.");
                }
                const partOut = await partnerRes.json();
                parent2_id = partOut.partner_id;
            }

            const res = await fetch("/api/relationships/child", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ tree_id: auth.tree_id, contributor_id: auth.contributor_id, parent1_id: selectedPersonId, child_name, child_gender, parent2_id })
            });
            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                throw new Error(errData.detail || "Failed to add child.");
            }
            const data = await res.json();
            
            // If subtype is adoptive, we must modify the relationship_subtype in the db
            if (subtype === "adoptive") {
                const linkRes = await fetch("/api/relationships/link", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        tree_id: auth.tree_id,
                        contributor_id: auth.contributor_id,
                        person1_id: selectedPersonId,
                        person2_id: data.child_id,
                        relationship_type: "parent-child",
                        relationship_subtype: "adoptive"
                    })
                });
                if (parent2_id) {
                    await fetch("/api/relationships/link", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            tree_id: auth.tree_id,
                            contributor_id: auth.contributor_id,
                            person1_id: parent2_id,
                            person2_id: data.child_id,
                            relationship_type: "parent-child",
                            relationship_subtype: "adoptive"
                        })
                    });
                }
            }
        } else {
            const child_id = document.getElementById("act-child-select-person").value;
            if (!child_id) throw new Error("Please select a child to link.");
            const res = await fetch("/api/relationships/link", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    tree_id: auth.tree_id,
                    contributor_id: auth.contributor_id,
                    person1_id: selectedPersonId,
                    person2_id: parseInt(child_id),
                    relationship_type: "parent-child",
                    relationship_subtype: subtype
                })
            });
            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                throw new Error(errData.detail || "Failed to link child.");
            }
        }
        showFeedback("Child linked successfully!");
        loadDashboard();
    } catch (err) {
        showFeedback(err.message || "Failed to add/link child.", "error");
    }
}

async function handleMergeSubmit(e) {
    e.preventDefault();
    const target_id = document.getElementById("act-merge-select-target").value;
    if (!target_id) {
        showFeedback("Please select a target profile to merge into.", "error");
        return;
    }
    
    if (!confirm("Are you sure you want to merge these profiles? This action will delete the duplicate profile and CANNOT be undone.")) {
        return;
    }
    
    try {
        const res = await fetch("/api/persons/merge", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                tree_id: auth.tree_id,
                contributor_id: auth.contributor_id,
                target_id: parseInt(target_id),
                duplicate_id: selectedPersonId
            })
        });
        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.detail || "Failed to merge profiles.");
        }
        showFeedback("Profiles merged successfully!");
        selectedPersonId = parseInt(target_id); // Select the merged target profile
        loadDashboard();
    } catch (err) {
        showFeedback(err.message || "Failed to merge profiles.", "error");
    }
}

async function handleDeleteConfirmAction() {
    try {
        const res = await fetch(`/api/trees/${auth.tree_id}/persons/${selectedPersonId}?contributor_id=${auth.contributor_id}`, {
            method: "DELETE"
        });
        if (res.status === 409) {
            // Trigger acknowledgment modal warning
            document.getElementById("modal-warning").style.display = "flex";
            showActionForm(null);
            return;
        }
        showFeedback("Member soft-deleted!");
        selectedPersonId = null;
        loadDashboard();
    } catch (err) {
        showFeedback("Failed to delete person.", "error");
    }
}

// ----------------- AUDIT LOGS OPERATIONS -----------------

async function loadActivityLogs() {
    try {
        const res = await fetch(`/api/trees/${auth.tree_id}/history?limit=5`);
        const logs = await res.json();
        const container = document.getElementById("activity-feed-list");
        container.innerHTML = "";

        if (logs.length === 0) {
            container.innerHTML = "<div style='color:#888; padding:5px 0;'>No edits recorded yet.</div>";
            return;
        }

        logs.forEach(log => {
            const ts = new Date(log.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) + " " + new Date(log.timestamp).toLocaleDateString([], { day: '2-digit', month: 'short' });
            const item = document.createElement("div");
            item.className = "activity-item";
            item.innerHTML = `<strong>${log.contributor_name}</strong>: ${log.details} <span class="activity-ts">(${ts})</span>`;
            container.appendChild(item);
        });
    } catch (err) {
        // Suppress audit logs load failures silently
    }
}

async function openHistoryModal() {
    try {
        const res = await fetch(`/api/trees/${auth.tree_id}/history?limit=100`);
        const logs = await res.json();
        const container = document.getElementById("modal-history-content");
        container.innerHTML = "";

        logs.forEach(log => {
            const ts = new Date(log.timestamp).toLocaleString();
            const div = document.createElement("div");
            div.style.padding = "8px 0";
            div.style.borderBottom = "1px solid #eee";
            div.innerHTML = `[${ts}] <strong>${log.contributor_name}</strong> (${log.contributor_email}): ${log.action} - ${log.details}`;
            container.appendChild(div);
        });

        document.getElementById("modal-history").style.display = "flex";
    } catch (err) {
        showFeedback("Failed to load audit history logs.", "error");
    }
}

// ----------------- EXPORT / IMPORT JSON -----------------

async function triggerJSONExport() {
    try {
        const res = await fetch(`/api/trees/${auth.tree_id}/export`);
        const data = await res.json();
        const jsonStr = JSON.stringify(data, null, 2);
        
        const blob = new Blob([jsonStr], { type: "application/json" });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = `${auth.tree_name.toLowerCase().replace(/ /g, '_')}_tree.json`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
        showFeedback("Exported JSON downloaded!");
    } catch (err) {
        showFeedback("Failed to export JSON.", "error");
    }
}

async function handleImportTree() {
    const fileInput = document.getElementById("import-file-input");
    const importName = document.getElementById("import-tree-name").value;
    const importPw = document.getElementById("import-tree-pw").value;
    const treeType = document.getElementById("import-tree-type").value;

    if (fileInput.files.length === 0 || !importName || !importPw) {
        showFeedback("JSON file, import tree name, and password are required!", "error");
        return;
    }

    const reader = new FileReader();
    reader.onload = async (e) => {
        try {
            const data = JSON.parse(e.target.result);
            const res = await fetch("/api/trees/import", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    tree_name: importName.strip(),
                    password: importPw,
                    creator_name: auth.contributor_name,
                    creator_email: auth.contributor_email,
                    data,
                    tree_type: treeType
                })
            });
            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                throw new Error(errData.detail || "Failed to import tree.");
            }
            const out = await res.json();
            
            auth.tree_id = out.tree_id;
            auth.tree_name = importName.strip();
            localStorage.setItem("auth", JSON.stringify(auth));
            
            selectedPersonId = out.selected_person_id;
            showFeedback("Tree imported successfully!");
            showPage("dashboard");
        } catch (err) {
            showFeedback(err.message || "Failed to import JSON data.", "error");
        }
    };
    reader.readAsText(fileInput.files[0]);
}

async function loadFamilyNavigator(personId) {
    const panel = document.getElementById("family-navigation-panel");
    const linksContainer = document.getElementById("family-nav-links");
    if (!panel || !linksContainer) return;

    try {
        const relRes = await fetch(`/api/trees/${auth.tree_id}/relationships`);
        const relationships = await relRes.json();

        const personsRes = await fetch(`/api/trees/${auth.tree_id}/persons`);
        const persons = await personsRes.json();
        const personsMap = {};
        persons.forEach(p => { personsMap[p.id] = p; });

        const links = [];
        
        relationships.forEach(r => {
            if (r.relationship_type === "partner") {
                if (r.person1_id === personId && personsMap[r.person2_id]) {
                    links.push({ rel: "Spouse", name: `${personsMap[r.person2_id].first_name} ${personsMap[r.person2_id].surname_now || ""}`, id: r.person2_id });
                } else if (r.person2_id === personId && personsMap[r.person1_id]) {
                    links.push({ rel: "Spouse", name: `${personsMap[r.person1_id].first_name} ${personsMap[r.person1_id].surname_now || ""}`, id: r.person1_id });
                }
            } else if (r.relationship_type === "parent-child") {
                if (r.person2_id === personId && personsMap[r.person1_id]) {
                    const parentGender = personsMap[r.person1_id].gender;
                    const relLabel = parentGender === "Male" ? "Father" : (parentGender === "Female" ? "Mother" : "Parent");
                    links.push({ rel: relLabel, name: `${personsMap[r.person1_id].first_name} ${personsMap[r.person1_id].surname_now || ""}`, id: r.person1_id });
                } else if (r.person1_id === personId && personsMap[r.person2_id]) {
                    links.push({ rel: "Child", name: `${personsMap[r.person2_id].first_name} ${personsMap[r.person2_id].surname_now || ""}`, id: r.person2_id });
                }
            } else if (r.relationship_type === "sibling") {
                if (r.person1_id === personId && personsMap[r.person2_id]) {
                    links.push({ rel: "Sibling", name: `${personsMap[r.person2_id].first_name} ${personsMap[r.person2_id].surname_now || ""}`, id: r.person2_id });
                } else if (r.person2_id === personId && personsMap[r.person1_id]) {
                    links.push({ rel: "Sibling", name: `${personsMap[r.person1_id].first_name} ${personsMap[r.person1_id].surname_now || ""}`, id: r.person1_id });
                }
            }
        });

        if (links.length === 0) {
            panel.style.display = "none";
            return;
        }

        panel.style.display = "block";
        linksContainer.innerHTML = "";
        links.forEach(l => {
            const btn = document.createElement("button");
            btn.className = "action-btn";
            btn.style.width = "100%";
            btn.style.textAlign = "left";
            btn.style.display = "flex";
            btn.style.justifyContent = "space-between";
            btn.style.alignItems = "center";
            btn.style.padding = "6px 12px";
            btn.style.fontSize = "12px";
            btn.style.background = "#fff";
            btn.style.color = "#2b6cb0";
            btn.style.border = "1px solid #bee3f8";
            btn.innerHTML = `<span><strong>${l.rel}:</strong> ${l.name}</span> <span style="font-size: 10px; color: #718096;">Center & Focus &rarr;</span>`;
            btn.addEventListener("click", () => {
                selectedPersonId = l.id;
                loadDashboard();
                if (network) {
                    network.focus(l.id, { scale: 1.0, animation: true });
                }
            });
            linksContainer.appendChild(btn);
        });
    } catch (err) {
        panel.style.display = "none";
    }
}

async function checkNameMatches(formType, inputId, suggestId, mode) {
    const input = document.getElementById(inputId);
    const suggestionsDiv = document.getElementById(suggestId);
    if (!input || !suggestionsDiv) return;

    const val = input.value.trim().toLowerCase();
    if (val.length < 2) {
        suggestionsDiv.style.display = "none";
        return;
    }

    try {
        const res = await fetch(`/api/trees/${auth.tree_id}/persons`);
        const persons = await res.json();

        const matches = persons.filter(p => {
            if (p.id === selectedPersonId) return false;
            const fname = (p.first_name || "").toLowerCase();
            const sname = (p.surname_now || "").toLowerCase();
            return fname.includes(val) || sname.includes(val);
        });

        if (matches.length === 0) {
            suggestionsDiv.style.display = "none";
            return;
        }

        suggestionsDiv.style.display = "block";
        suggestionsDiv.innerHTML = `<div style="font-weight: bold; margin-bottom: 4px; color: #2b6cb0;">Possible Matches Already in Tree:</div>`;

        matches.slice(0, 3).forEach(p => {
            const row = document.createElement("div");
            row.style.display = "flex";
            row.style.justifyContent = "space-between";
            row.style.alignItems = "center";
            row.style.padding = "4px 0";
            row.style.borderBottom = "1px solid #e2e8f0";
            row.innerHTML = `
                <span>${p.first_name} ${p.surname_now || ""} (ID: ${p.id})</span>
                <button type="button" style="background: #3182ce; color: white; border: none; padding: 2px 6px; border-radius: 3px; font-size: 10px; cursor: pointer;">Link Profile</button>
            `;
            row.querySelector("button").addEventListener("click", () => {
                linkMatchedPerson(formType, p.id, mode);
                suggestionsDiv.style.display = "none";
                input.value = "";
            });
            suggestionsDiv.appendChild(row);
        });
    } catch (err) {
        suggestionsDiv.style.display = "none";
    }
}

function linkMatchedPerson(formType, personId, mode) {
    showFeedback(`Switched mode to link profile ID: ${personId}`);
    if (formType === "parents") {
        if (mode === "father") {
            document.getElementById("act-parents-mode").value = "link_father";
            toggleFormMode("parents");
            populateExistingPersonsSelects().then(() => {
                document.getElementById("act-parents-select-father").value = personId;
            });
        } else if (mode === "mother") {
            document.getElementById("act-parents-mode").value = "link_mother";
            toggleFormMode("parents");
            populateExistingPersonsSelects().then(() => {
                document.getElementById("act-parents-select-mother").value = personId;
            });
        }
    } else if (formType === "sibling") {
        document.getElementById("act-sibling-mode").value = "link";
        toggleFormMode("sibling");
        populateExistingPersonsSelects().then(() => {
            document.getElementById("act-sibling-select-person").value = personId;
        });
    } else if (formType === "partner") {
        document.getElementById("act-partner-mode").value = "link";
        toggleFormMode("partner");
        populateExistingPersonsSelects().then(() => {
            document.getElementById("act-partner-select-person").value = personId;
        });
    } else if (formType === "child") {
        document.getElementById("act-child-mode").value = "link";
        toggleFormMode("child");
        populateExistingPersonsSelects().then(() => {
            document.getElementById("act-child-select-person").value = personId;
        });
    }
}

// Javascript String clean helper
String.prototype.strip = function() {
    return this.replace(/^\s+|\s+$/g, '');
};

// Undo / Redo Operations

async function updateUndoRedoStatus() {
    const btnUndo = document.getElementById("tb-undo");
    const btnRedo = document.getElementById("tb-redo");
    
    if (!auth || !auth.tree_id) {
        if (btnUndo) btnUndo.disabled = true;
        if (btnRedo) btnRedo.disabled = true;
        return;
    }
    
    try {
        const res = await fetch(`/api/trees/${auth.tree_id}/undo-redo-status`);
        if (!res.ok) return;
        
        const data = await res.json();
        if (btnUndo) {
            btnUndo.disabled = !data.can_undo;
            btnUndo.title = data.can_undo ? `Undo: ${data.undo_action}` : "Nothing to undo";
        }
        if (btnRedo) {
            btnRedo.disabled = !data.can_redo;
            btnRedo.title = data.can_redo ? `Redo: ${data.redo_action}` : "Nothing to redo";
        }
    } catch (err) {
        console.error("Failed to fetch undo/redo status:", err);
    }
}

async function handleUndoClick() {
    if (!auth) return;
    try {
        const res = await fetch(`/api/trees/${auth.tree_id}/undo`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ contributor_id: auth.contributor_id })
        });
        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.detail || "Failed to perform undo.");
        }
        const data = await res.json();
        showFeedback(data.message + " (" + data.action + ")");
        
        network = null;
        await loadDashboard();
    } catch (err) {
        showFeedback(err.message, "error");
    }
}

async function handleRedoClick() {
    if (!auth) return;
    try {
        const res = await fetch(`/api/trees/${auth.tree_id}/redo`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ contributor_id: auth.contributor_id })
        });
        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.detail || "Failed to perform redo.");
        }
        const data = await res.json();
        showFeedback(data.message + " (" + data.action + ")");
        
        network = null;
        await loadDashboard();
    } catch (err) {
        showFeedback(err.message, "error");
    }
}

// Run Initializer
init();