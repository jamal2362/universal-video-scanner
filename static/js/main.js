// i18n System
let currentLang = 'de';
let translations = {};

async function loadTranslations(lang) {
    try {
        const response = await fetch(`/static/locale/${lang}.json`);
        if (!response.ok) throw new Error('Translation file not found');
        translations = await response.json();
        return true;
    } catch (error) {
        console.error('Error loading translations:', error);
        return false;
    }
}

function t(key, replacements = {}) {
    let text = translations[key] || key;
    for (const [placeholder, value] of Object.entries(replacements)) {
        text = text.replace(`{${placeholder}}`, value);
    }
    return text;
}

function applyTranslations() {
    // Text content
    document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.getAttribute('data-i18n');
        if (translations[key]) {
            // For option elements, set text property; for others, set textContent
            if (el.tagName === 'OPTION') {
                el.text = translations[key];
            } else {
                el.textContent = translations[key];
            }
        }
    });
    
    // HTML content
    document.querySelectorAll('[data-i18n-html]').forEach(el => {
        const key = el.getAttribute('data-i18n-html');
        if (translations[key]) el.innerHTML = translations[key];
    });
    
    // Placeholder attributes
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
        const key = el.getAttribute('data-i18n-placeholder');
        if (translations[key]) el.placeholder = translations[key];
    });
    
    // Data labels
    document.querySelectorAll('[data-label-i18n]').forEach(el => {
        const key = el.getAttribute('data-label-i18n');
        if (translations[key]) el.setAttribute('data-label', translations[key]);
    });
    
    // Aria labels
    document.querySelectorAll('[data-aria-label-i18n]').forEach(el => {
        const key = el.getAttribute('data-aria-label-i18n');
        if (translations[key]) el.setAttribute('aria-label', translations[key]);
    });
    
    updateLanguageButtons();
}

function updateLanguageButtons() {
    const langDe = document.getElementById('langDe');
    const langEn = document.getElementById('langEn');
    if (langDe && langEn) {
        langDe.classList.toggle('active', currentLang === 'de');
        langEn.classList.toggle('active', currentLang === 'en');
    }
}

async function setLanguage(lang) {
    currentLang = lang;
    localStorage.setItem('dovi_language', lang);
    document.documentElement.lang = lang;
    const loaded = await loadTranslations(lang);
    if (loaded) {
        applyTranslations();
        loadFileList(); // Update dropdown
    }
}

async function initLanguage() {
    const savedLang = localStorage.getItem('dovi_language') || 'de';
    currentLang = savedLang;
    document.documentElement.lang = savedLang;
    await loadTranslations(savedLang);
    applyTranslations();
}

// Existing functions (startManualScan, loadFileList, scanSelectedFile) remain unchanged.
// The script is extended with sorting logic and initialization.

function startManualScan() {
    const button = document.getElementById('scanButton');
    const loading = document.getElementById('loadingIndicator');
    const message = document.getElementById('message');
    
    // Disable button and show loading
    button.disabled = true;
    loading.classList.add('active');
    message.style.display = 'none';
    
    // Make AJAX request to scan endpoint
    fetch('/scan', {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        // Hide loading
        loading.classList.remove('active');
        button.disabled = false;
        
        // Show message
        message.className = 'message';
        if (data.new_files > 0) {
            message.classList.add('success');
            message.textContent = `✓ ${t('scan_complete', { count: data.new_files })}`;
        } else {
            message.classList.add('info');
            message.textContent = `ℹ ${t('no_new_files')}`;
        }
        message.style.display = 'block';
        
        // Reload page if new files were found
        if (data.new_files > 0) {
            setTimeout(() => {
                location.reload();
            }, 2000);
        }
    })
    .catch(error => {
        loading.classList.remove('active');
        button.disabled = false;
        message.className = 'message';
        message.style.display = 'block';
        message.textContent = `✗ ${t('scan_error')}: ${error}`;
    });
}

function loadFileList() {
    fetch('/get_files')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                const select = document.getElementById('fileSelect');
                // Clear existing options except first
                select.innerHTML = `<option value="">${t('select_file')}</option>`;
                
                // Add files to dropdown
                data.files.forEach(file => {
                    const option = document.createElement('option');
                    option.value = file.path;
                    option.textContent = file.name + (file.scanned ? ' ✓' : '');
                    if (file.scanned) {
                        option.style.color = '#4ecca3';
                    }
                    select.appendChild(option);
                });

                // enable scan for selected file when choosing
				select.addEventListener('change', function() {
					const scanBtn = document.getElementById('scanFileButton');
					if (this.value) {
						scanBtn.classList.remove('hidden');
						scanBtn.disabled = false;
					} else {
						scanBtn.classList.add('hidden');
						scanBtn.disabled = true;
					}
				});
            }
        })
        .catch(error => {
            console.error('Error loading file list:', error);
        });
}

function scanSelectedFile() {
    const select = document.getElementById('fileSelect');
    const filePath = select.value;
    
    if (!filePath) {
        return;
    }
    
    const button = document.getElementById('scanFileButton');
    const loading = document.getElementById('loadingIndicator');
    const message = document.getElementById('message');
    
    // Disable button and show loading
    button.disabled = true;
    loading.classList.add('active');
    message.style.display = 'none';
    
    // Make AJAX request to scan specific file
    fetch('/scan_file', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ file_path: filePath })
    })
    .then(response => response.json())
    .then(data => {
        // Hide loading
        loading.classList.remove('active');
        button.disabled = false;
        
        // Show message
        message.className = 'message';
        if (data.success) {
            message.classList.add('success');
            message.textContent = '✓ ' + data.message;
            
            // Reload file list and page
            loadFileList();
            setTimeout(() => {
                location.reload();
            }, 2000);
        } else {
            message.classList.add('info');
            message.textContent = 'ℹ ' + data.message;
        }
        message.style.display = 'block';
    })
    .catch(error => {
        loading.classList.remove('active');
        button.disabled = false;
        message.className = 'message';
        message.style.display = 'block';
        message.textContent = `✗ ${t('file_scan_error')}: ${error}`;
    });
}

/* -------------------------------
   New Sorting Logic (client-side)
   ------------------------------- */

// Real-time search function
function searchMedia() {
    const searchTerm = document.getElementById('searchInput').value.toLowerCase();
    const rows = document.querySelectorAll('#mediaTable tbody tr');
    
    rows.forEach(row => {
        // Get searchable content from specific cells only
        const posterCell = row.querySelector('td:nth-child(1)');
        const hdrCell = row.querySelector('td:nth-child(2)');
        const resolutionCell = row.querySelector('td:nth-child(3)');
        const audioCell = row.querySelector('td:nth-child(4)');
        
        // Build searchable text from relevant content
        let searchableText = '';
        
        // From poster cell: get title or filename
        if (posterCell) {
            const posterTitle = posterCell.querySelector('.poster-title');
            const filenameFallback = posterCell.querySelector('.filename-fallback');
            if (posterTitle) {
                searchableText += posterTitle.textContent + ' ';
            } else if (filenameFallback) {
                searchableText += filenameFallback.textContent + ' ';
            } else {
                // Fallback to title attribute
                const title = posterCell.getAttribute('title');
                if (title) searchableText += title + ' ';
            }
        }
        
        // From other cells: get text content
        if (hdrCell) searchableText += hdrCell.textContent + ' ';
        if (resolutionCell) searchableText += resolutionCell.textContent + ' ';
        if (audioCell) searchableText += audioCell.textContent + ' ';
        
        // Check if search term is in the searchable text
        row.style.display = searchableText.toLowerCase().includes(searchTerm) ? '' : 'none';
    });
}

function getProfileRank(hdrFormat, hdrDetail, elType) {
    // Normalize strings
    const f = (hdrFormat || '').toLowerCase();
    const d = (hdrDetail || '').toLowerCase();
    const e = (elType || '').toLowerCase();

    // 0: Profile 7 FEL
    if ((d.includes('profile 7') || d.includes('prof 7') || d.includes('p7') || d.includes('profile7') || f.includes('dolby vision') || f.includes('dolby')) && e.includes('fel')) {
        return 0;
    }
    // 1: Profile 7 MEL
    if ((d.includes('profile 7') || d.includes('prof 7') || d.includes('p7') || d.includes('profile7') || f.includes('dolby vision') || f.includes('dolby')) && e.includes('mel')) {
        return 1;
    }
    // 2: Profile 8
    if (d.includes('profile 8') || d.includes('profile8') || d.includes('p8') || f.includes('profile 8') || f.includes('p8') ) {
        return 2;
    }
    // 3: Profile 5
    if (d.includes('profile 5') || d.includes('profile5') || d.includes('p5') ) {
        return 3;
    }
    // 4: HDR10+
    if (f.includes('hdr10+') || d.includes('hdr10+') || f.includes('hdr10plus') || d.includes('hdr10plus')) {
        return 4;
    }
    // 5: HDR (HDR10 or HLG)
    if (f.includes('hdr10') || d.includes('hdr10') || f.includes('hlg') || d.includes('hlg') || f.includes('smpte2084') || d.includes('smpte2084')) {
        return 5;
    }
    // 6: SDR
    if (f.includes('sdr') || d.includes('sdr')) {
        return 6;
    }
    // 7: fallback / unknown
    return 7;
}

function getFilenameFromRow(row) {
    // Try multiple places: title attribute, .poster-title, .filename-fallback
    const td = row.querySelector('td[data-label="Poster / Dateiname"]');
    if (!td) return '';
    // title attribute on td
    if (td.getAttribute('title')) return td.getAttribute('title').trim();
    const posterTitle = td.querySelector('.poster-title');
    if (posterTitle) return posterTitle.textContent.trim();
    const fallback = td.querySelector('.filename-fallback');
    if (fallback) return fallback.textContent.trim();
    return td.textContent.trim();
}

function sortTableByProfile() {
    const table = document.getElementById('mediaTable');
    if (!table) return;
    const tbody = table.querySelector('tbody');
    const rows = Array.from(tbody.querySelectorAll('tr'));

    rows.sort((a, b) => {
        const aFmt = a.getAttribute('data-hdr-format') || '';
        const aDet = a.getAttribute('data-hdr-detail') || '';
        const aEl  = a.getAttribute('data-el-type') || '';

        const bFmt = b.getAttribute('data-hdr-format') || '';
        const bDet = b.getAttribute('data-hdr-detail') || '';
        const bEl  = b.getAttribute('data-el-type') || '';

        const aRank = getProfileRank(aFmt, aDet, aEl);
        const bRank = getProfileRank(bFmt, bDet, bEl);

        if (aRank !== bRank) return aRank - bRank;

        // If same priority, sort secondarily by filename
        const aName = getFilenameFromRow(a).toLowerCase();
        const bName = getFilenameFromRow(b).toLowerCase();
        if (aName < bName) return -1;
        if (aName > bName) return 1;
        return 0;
    });

    // Rearrange order in DOM
    rows.forEach(r => tbody.appendChild(r));
}

function sortTableByFilename() {
    const table = document.getElementById('mediaTable');
    if (!table) return;
    const tbody = table.querySelector('tbody');
    const rows = Array.from(tbody.querySelectorAll('tr'));

    rows.sort((a, b) => {
        const aName = getFilenameFromRow(a).toLowerCase();
        const bName = getFilenameFromRow(b).toLowerCase();
        if (aName < bName) return -1;
        if (aName > bName) return 1;
        return 0;
    });

    rows.forEach(r => tbody.appendChild(r));
}

function getAudioCodecFromRow(row) {
    // Get audio codec from the audio cell
    const audioCell = row.querySelector('td.audio-codec');
    if (!audioCell) return '';
    return audioCell.textContent.trim();
}

function getAudioRank(audioCodec) {
    // Normalize audio codec string
    const audio = (audioCodec || '').toLowerCase();
    
    // Priority ranking based on audio quality/format
    // 0: Dolby TrueHD (Atmos)
    if (audio.includes('truehd') && audio.includes('atmos')) {
        return 0;
    }
    // 1: DTS:X
    if (audio.includes('dts:x') || audio.includes('dts-x') || audio.includes('dtsx')) {
        return 1;
    }
    // 2: Dolby TrueHD
    if (audio.includes('truehd')) {
        return 2;
    }
    // 3: DTS-HD MA
    if (audio.includes('dts-hd ma') || audio.includes('dts-hd master audio')) {
        return 3;
    }
    // 4: DTS-HD HRA
    if (audio.includes('dts-hd hra') || audio.includes('dts-hd high resolution')) {
        return 4;
    }
    // 5: Dolby Digital Plus (Atmos)
    if (audio.includes('digital plus') && audio.includes('atmos')) {
        return 5;
    }
    // 6: Dolby Digital Plus
    if (audio.includes('digital plus')) {
        return 6;
    }
    // 7: DTS (but not DTS-HD or DTS:X)
    if (audio.includes('dts') && !audio.includes('dts-hd') && !audio.includes('dts:x') && !audio.includes('dts-x')) {
        return 7;
    }
    // 8: Dolby Digital (but not Plus)
    if ((audio.includes('dolby digital') || audio.includes('ac-3')) && !audio.includes('plus')) {
        return 8;
    }
    // 9+: Other formats (AAC, FLAC, MP3, PCM, etc.)
    return 9;
}

function sortTableByAudio() {
    const table = document.getElementById('mediaTable');
    if (!table) return;
    const tbody = table.querySelector('tbody');
    const rows = Array.from(tbody.querySelectorAll('tr'));

    rows.sort((a, b) => {
        const aAudio = getAudioCodecFromRow(a);
        const bAudio = getAudioCodecFromRow(b);
        
        const aRank = getAudioRank(aAudio);
        const bRank = getAudioRank(bAudio);
        
        if (aRank !== bRank) return aRank - bRank;
        
        // If same rank, sort alphabetically by codec name
        const aLower = aAudio.toLowerCase();
        const bLower = bAudio.toLowerCase();
        if (aLower < bLower) return -1;
        if (aLower > bLower) return 1;
        
        // If same audio codec, sort secondarily by filename
        const aName = getFilenameFromRow(a).toLowerCase();
        const bName = getFilenameFromRow(b).toLowerCase();
        if (aName < bName) return -1;
        if (aName > bName) return 1;
        return 0;
    });

    rows.forEach(r => tbody.appendChild(r));
}

function applySort(mode) {
    if (!mode) mode = localStorage.getItem('dovi_sort_mode') || 'filename';
    const select = document.getElementById('sortSelect');
    if (select) select.value = mode;

    if (mode === 'profile') {
        sortTableByProfile();
    } else if (mode === 'audio') {
        sortTableByAudio();
    } else {
        sortTableByFilename();
    }
}

document.addEventListener('DOMContentLoaded', function() {
    // Initialize language first
    initLanguage().then(() => {
        // Load file list for scan dropdown
        loadFileList();

        // Apply initial sorting
        applySort();

        // Listener for sort selection
        const sortSelect = document.getElementById('sortSelect');
        if (sortSelect) {
            sortSelect.addEventListener('change', function() {
                const mode = this.value || 'filename';
                localStorage.setItem('dovi_sort_mode', mode);
                applySort(mode);
            });
        }
        
        // Listener for search bar
        const searchInput = document.getElementById('searchInput');
        if (searchInput) {
            searchInput.addEventListener('input', searchMedia);
        }
    });
});
