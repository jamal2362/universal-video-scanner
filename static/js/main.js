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
    const buttonText = document.getElementById('scanButtonText');
    const message = document.getElementById('message');

    // Disable button + blue background
    button.disabled = true;
    button.classList.add('scanning');
    buttonText.textContent = t('scanning');
    if (message) message.style.display = 'none';

    fetch('/scan', { method: 'POST' })
        .then(response => {
            if (!response.ok) throw new Error('Server error');
            return response.json();
        })
        .then(data => {
            if (!message) return;

            message.className = 'message';
            if (data.new_files > 0) {
                message.classList.add('success');
                message.textContent = `✓ ${t('scan_complete', { count: data.new_files })}`;
                setTimeout(() => location.reload(), 2000);
            } else {
                message.classList.add('info');
                message.textContent = `ℹ ${t('no_new_files')}`;
				setTimeout(() => location.reload(), 2000);
            }
            message.style.display = 'block';
        })
        .catch(error => {
            if (!message) return;
            message.className = 'message error';
            message.textContent = `✗ ${t('scan_error')}`;
            message.style.display = 'block';
            console.error(error);
        })
        .finally(() => {
            button.disabled = false;
            button.classList.remove('scanning');
            buttonText.textContent = t('scan_all_button');
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
    
    let visibleRowCount = 0;
    
    rows.forEach(row => {
        // Get searchable content from specific cells only
        const posterCell = row.querySelector('td:nth-child(1)');
        const hdrCell = row.querySelector('td:nth-child(2)');
        const audioCell = row.querySelector('td:nth-child(3)');
        const resolutionCell = row.querySelector('td:nth-child(4)');
        
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
        const isVisible = searchableText.toLowerCase().includes(searchTerm);
        row.style.display = isVisible ? '' : 'none';
        
        if (isVisible) {
            visibleRowCount++;
        }
    });
    
    // Handle table header and no-results message visibility
    const table = document.getElementById('mediaTable');
    const thead = table ? table.querySelector('thead') : null;
    
    if (searchTerm && visibleRowCount === 0) {
        // Hide table header when no results
        if (thead) {
            thead.style.display = 'none';
        }
        
        // Show or create no-results message
        let noResultsMsg = document.getElementById('search-no-results');
        if (!noResultsMsg) {
            noResultsMsg = document.createElement('div');
            noResultsMsg.id = 'search-no-results';
            noResultsMsg.className = 'empty-state';
            
            const heading = document.createElement('h2');
            heading.textContent = t('search_no_results');
            noResultsMsg.appendChild(heading);
            
            // Insert after the table
            if (table && table.parentNode) {
                table.parentNode.insertBefore(noResultsMsg, table.nextSibling);
            }
        }
        noResultsMsg.style.display = 'block';
    } else {
        // Show table header when there are results or no search term
        if (thead) {
            thead.style.display = '';
        }
        
        // Hide no-results message
        const noResultsMsg = document.getElementById('search-no-results');
        if (noResultsMsg) {
            noResultsMsg.style.display = 'none';
        }
    }
    
    // Update clear button visibility
    updateClearButton();
    // Update profile stats based on visible rows
    updateProfileStats();
}

// Clear search function
function clearSearch() {
    const searchInput = document.getElementById('searchInput');
    searchInput.value = '';
    searchMedia(); // Re-run search to show all rows
}

// Update clear button visibility
function updateClearButton() {
    const searchInput = document.getElementById('searchInput');
    const clearBtn = document.getElementById('clearSearch');
    if (clearBtn) {
        clearBtn.style.display = searchInput.value.length > 0 ? 'block' : 'none';
    }
}

// Update profile statistics
function updateProfileStats() {
    const table = document.getElementById('mediaTable');
    if (!table) return;
    
    const rows = Array.from(table.querySelectorAll('tbody tr'));
    const visibleRows = rows.filter(row => row.style.display !== 'none');
    
    const stats = {
        FEL: 0,
        MEL: 0,
        'Profile 8': 0,
        'Profile 5': 0,
        'HDR10+': 0,
        'HDR10': 0,
        'HLG': 0,
        'SDR': 0
    };
    
    visibleRows.forEach(row => {
        const elType = (row.getAttribute('data-el-type') || '').toUpperCase();
        const hdrFormat = (row.getAttribute('data-hdr-format') || '').toLowerCase();
        const hdrDetail = (row.getAttribute('data-hdr-detail') || '').toLowerCase();
        
        // Check for FEL or MEL
        if (elType === 'FEL') {
            stats.FEL++;
        } else if (elType === 'MEL') {
            stats.MEL++;
        } 
        // Check for Profile 8
        else if (
            hdrDetail.includes('profile 8') ||
            hdrDetail.includes('profile8') ||
            hdrDetail.includes('p8') ||
            hdrFormat.includes('profile 8') ||
            hdrFormat.includes('p8')
        ) {
            stats['Profile 8']++;
        }
        // Check for Profile 5
        else if (
            hdrDetail.includes('profile 5') ||
            hdrDetail.includes('profile5') ||
            hdrDetail.includes('p5')
        ) {
            stats['Profile 5']++;
        }
        // Check for HDR10+ (must check before HDR10 to avoid false matches)
        else if (
            hdrFormat.includes('hdr10+') ||
            hdrDetail.includes('hdr10+') ||
            hdrFormat.includes('hdr10plus') ||
            hdrDetail.includes('hdr10plus')
        ) {
            stats['HDR10+']++;
        }
        // Check for HDR10 (but not HDR10+) - explicitly exclude HDR10+
        else if (
            (hdrFormat.includes('hdr10') ||
             hdrDetail.includes('hdr10') ||
             hdrFormat.includes('smpte2084')) &&
            !hdrFormat.includes('hdr10+') &&
            !hdrDetail.includes('hdr10+') &&
            !hdrFormat.includes('hdr10plus') &&
            !hdrDetail.includes('hdr10plus')
        ) {
            stats['HDR10']++;
        }
        // Check for HLG
        else if (hdrFormat.includes('hlg') || hdrDetail.includes('hlg')) {
            stats['HLG']++;
        }
        // Check for SDR
        else if (hdrFormat.includes('sdr') || hdrDetail.includes('sdr')) {
            stats['SDR']++;
        }
    });
    
    // Build stats string (only show profiles with at least 1 title)
    const statsArray = [];
    if (stats.FEL > 0) statsArray.push(`FEL: <strong>${stats.FEL}</strong>`);
    if (stats.MEL > 0) statsArray.push(`MEL: <strong>${stats.MEL}</strong>`);
    if (stats['Profile 8'] > 0) statsArray.push(`P8: <strong>${stats['Profile 8']}</strong>`);
    if (stats['Profile 5'] > 0) statsArray.push(`P5: <strong>${stats['Profile 5']}</strong>`);
    if (stats['HDR10+'] > 0) statsArray.push(`HDR10+: <strong>${stats['HDR10+']}</strong>`);
    if (stats['HDR10'] > 0) statsArray.push(`HDR10: <strong>${stats['HDR10']}</strong>`);
    if (stats['HLG'] > 0) statsArray.push(`HLG: <strong>${stats['HLG']}</strong>`);
    if (stats['SDR'] > 0) statsArray.push(`SDR: <strong>${stats['SDR']}</strong>`);
    const profileStatsElement = document.getElementById('profileStats');
    if (profileStatsElement && statsArray.length > 0) {
        profileStatsElement.innerHTML = statsArray.join(' / ');
    } else if (profileStatsElement) {
        profileStatsElement.innerHTML = '';
    }
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
    const td = row.querySelector('td[data-label-i18n="table_header_poster"]');
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

function sortTableByProfileAudio() {
    const table = document.getElementById('mediaTable');
    if (!table) return;
    const tbody = table.querySelector('tbody');
    const rows = Array.from(tbody. querySelectorAll('tr'));

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

        const aAudio = getAudioCodecFromRow(a);
        const bAudio = getAudioCodecFromRow(b);
        const aAudioRank = getAudioRank(aAudio);
        const bAudioRank = getAudioRank(bAudio);

        if (aAudioRank !== bAudioRank) return aAudioRank - bAudioRank;

        const aName = getFilenameFromRow(a).toLowerCase();
        const bName = getFilenameFromRow(b).toLowerCase();
        if (aName < bName) return -1;
        if (aName > bName) return 1;
        return 0;
    });

    rows.forEach(r => tbody.appendChild(r));
}

function sortTableByProfileVideoBitrate() {
    const table = document.getElementById('mediaTable');
    if (!table) return;
    const tbody = table.querySelector('tbody');
    const rows = Array.from(tbody.querySelectorAll('tr'));

    rows.sort((a, b) => {
        const aFmt = a. getAttribute('data-hdr-format') || '';
        const aDet = a. getAttribute('data-hdr-detail') || '';
        const aEl  = a. getAttribute('data-el-type') || '';

        const bFmt = b.getAttribute('data-hdr-format') || '';
        const bDet = b.getAttribute('data-hdr-detail') || '';
        const bEl  = b.getAttribute('data-el-type') || '';

        const aRank = getProfileRank(aFmt, aDet, aEl);
        const bRank = getProfileRank(bFmt, bDet, bEl);

        if (aRank !== bRank) return aRank - bRank;

        const aVideoBitrate = parseFloat(a.getAttribute('data-video-bitrate')) || 0;
        const bVideoBitrate = parseFloat(b.getAttribute('data-video-bitrate')) || 0;

        if (bVideoBitrate !== aVideoBitrate) return bVideoBitrate - aVideoBitrate;

        const aName = getFilenameFromRow(a).toLowerCase();
        const bName = getFilenameFromRow(b).toLowerCase();
        if (aName < bName) return -1;
        if (aName > bName) return 1;
        return 0;
    });

    rows.forEach(r => tbody.appendChild(r));
}

function sortTableByProfileAudioBitrate() {
    const table = document.getElementById('mediaTable');
    if (!table) return;
    const tbody = table.querySelector('tbody');
    const rows = Array.from(tbody.querySelectorAll('tr'));

    rows.sort((a, b) => {
        const aFmt = a.getAttribute('data-hdr-format') || '';
        const aDet = a.getAttribute('data-hdr-detail') || '';
        const aEl  = a.getAttribute('data-el-type') || '';

        const bFmt = b. getAttribute('data-hdr-format') || '';
        const bDet = b. getAttribute('data-hdr-detail') || '';
        const bEl  = b. getAttribute('data-el-type') || '';

        const aRank = getProfileRank(aFmt, aDet, aEl);
        const bRank = getProfileRank(bFmt, bDet, bEl);

        if (aRank !== bRank) return aRank - bRank;

        const aAudioBitrate = parseFloat(a.getAttribute('data-audio-bitrate')) || 0;
        const bAudioBitrate = parseFloat(b.getAttribute('data-audio-bitrate')) || 0;

        if (bAudioBitrate !== aAudioBitrate) return bAudioBitrate - aAudioBitrate;

        const aName = getFilenameFromRow(a).toLowerCase();
        const bName = getFilenameFromRow(b).toLowerCase();
        if (aName < bName) return -1;
        if (aName > bName) return 1;
        return 0;
    });

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
    if (audio.includes('dts') && !audio.includes('dts-hd') && !audio.includes('dts:x') && !audio.includes('dts-x') && !audio.includes('dtsx')) {
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

function sortTableByRating() {
    sortTableByNumericAttribute('data-tmdb-rating');
}

function sortTableByFileSize() {
    sortTableByNumericAttribute('data-file-size');
}

function sortTableByVideoBitrate() {
    sortTableByNumericAttribute('data-video-bitrate');
}

function sortTableByAudioBitrate() {
    sortTableByNumericAttribute('data-audio-bitrate');
}

function sortTableByNumericAttribute(attribute) {
    const table = document.getElementById('mediaTable');
    if (!table) return;
    const tbody = table.querySelector('tbody');
    const rows = Array.from(tbody.querySelectorAll('tr'));

    rows.sort((a, b) => {
        const aValue = parseFloat(a.getAttribute(attribute)) || 0;
        const bValue = parseFloat(b.getAttribute(attribute)) || 0;
        
        // Sort descending (highest/largest first)
        if (bValue !== aValue) return bValue - aValue;
        
        // If same value, sort secondarily by filename
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
    } else if (mode === 'profile_audio') {
        sortTableByProfileAudio();
    } else if (mode === 'profile_videobitrate') {
        sortTableByProfileVideoBitrate();
    } else if (mode === 'profile_audiobitrate') {
        sortTableByProfileAudioBitrate();
    } else if (mode === 'audio') {
        sortTableByAudio();
    } else if (mode === 'rating') {
        sortTableByRating();
    } else if (mode === 'filesize') {
        sortTableByFileSize();
    } else if (mode === 'videobitrate') {
        sortTableByVideoBitrate();
    } else if (mode === 'audiobitrate') {
        sortTableByAudioBitrate();
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

        // Update profile statistics on initial load
        updateProfileStats();
        
        // Update clear button state on initial load
        updateClearButton();

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
        
        // Listener for file select change
        const fileSelect = document.getElementById('fileSelect');
        if (fileSelect) {
            fileSelect.addEventListener('change', function() {
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
        
        // Listener for Escape key to close dialog
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') {
                const overlay = document.getElementById('mediaDialogOverlay');
                if (overlay && overlay.classList.contains('active')) {
                    closeMediaDialog();
                }
            }
        });
        
        // Set up Server-Sent Events for real-time deletion updates
        setupSSE();
    });
});

/* -------------------------------
   Server-Sent Events for Live Updates
   ------------------------------- */

function setupSSE() {
    if (typeof EventSource === 'undefined') {
        console.warn('EventSource not supported by browser');
        return;
    }
    
    const eventSource = new EventSource('/events');
    
    eventSource.addEventListener('file_deleted', function(e) {
        try {
            const data = JSON.parse(e.data);
            const filePath = data.file_path;
            
            if (filePath) {
                removeFileFromTable(filePath);
            }
        } catch (error) {
            console.error('Error parsing deletion event:', error);
        }
    });
    
    eventSource.onerror = function(e) {
        console.error('SSE connection error:', e);
        // EventSource will automatically try to reconnect
    };
}

function removeFileFromTable(filePath) {
    // Find the table row that corresponds to the deleted file
    const table = document.getElementById('mediaTable');
    if (!table) return;
    
    const rows = table.querySelectorAll('tbody tr');
    
    for (const row of rows) {
        // Try to find the title attribute which contains the filename
        const posterCell = row.querySelector('td[data-label-i18n="table_header_poster"]');
        if (posterCell && posterCell.getAttribute('title') === filePath) {
            row.remove();
            updateFileCount();
            updateProfileStats();
            console.log(`Removed deleted file from table: ${filePath}`);
            return;
        }
        
        // Fallback: check if filename matches (without full path)
        const filename = filePath.split('/').pop();
        if (posterCell && posterCell.getAttribute('title') === filename) {
            row.remove();
            updateFileCount();
            updateProfileStats();
            console.log(`Removed deleted file from table: ${filename}`);
            return;
        }
    }
}

function updateFileCount() {
    const table = document.getElementById('mediaTable');
    if (!table) return;
    
    const visibleRows = table.querySelectorAll('tbody tr:not([style*="display: none"])');
    const fileCountElement = document.getElementById('fileCount');
    
    if (fileCountElement) {
        const count = visibleRows.length;
        fileCountElement.innerHTML = `${count} <span data-i18n="media_count"></span>`;
        applyTranslations();
    }
}

/* -------------------------------
   Media Details Dialog Functions
   ------------------------------- */

function formatDuration(seconds) {
    if (!seconds || seconds <= 0) return 'Unknown';
    
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    
    if (hours > 0) {
        return `${hours}h ${minutes}m`;
    } else {
        const secs = Math.floor(seconds % 60);
        return `${minutes}m ${secs}s`;
    }
}

function formatFileSize(bytes) {
    if (bytes === null || bytes === undefined || bytes < 0) return 'Unknown';
    
    // Always convert to GB
    const GB_IN_BYTES = 1024 * 1024 * 1024;
    const sizeInGB = bytes / GB_IN_BYTES;
    
    // Format with 1 decimal place and use appropriate decimal separator based on locale
    const formattedSize = currentLang === 'de' 
        ? sizeInGB.toFixed(1).replace('.', ',')  // German: comma
        : sizeInGB.toFixed(1);                    // English: period
    return `${formattedSize} GB`;
}

function showMediaDialog(title, year, duration, videoBitrate, audioBitrate, fileSize, posterUrl, tmdbId, plot, directors, cast, tmdbRating) {
    const overlay = document.getElementById('mediaDialogOverlay');
    const dialogTitle = document.getElementById('dialogTitle');
    const dialogDuration = document.getElementById('dialogDuration');
    const dialogFileSize = document.getElementById('dialogFileSize');
    const dialogVideoBitrate = document.getElementById('dialogVideoBitrate');
    const dialogAudioBitrate = document.getElementById('dialogAudioBitrate');
    const dialogPoster = document.getElementById('dialogPoster');
    const dialogPosterImg = document.getElementById('dialogPosterImg');
    const dialogTmdbBadge = document.getElementById('dialogTmdbBadge');
    const dialogTmdbRatingElement = document.getElementById('dialogTmdbRating');
    const dialogTmdbLink = document.getElementById('dialogTmdbLink');
    const dialogTrailer = document.getElementById('dialogTrailer');
    const dialogTrailerLink = document.getElementById('dialogTrailerLink');
    const dialogLinksContainer = document.getElementById('dialogLinksContainer');
    const dialogPlot = document.getElementById('dialogPlot');
    const dialogPlotText = document.getElementById('dialogPlotText');
    const dialogDirectors = document.getElementById('dialogDirectors');
    const dialogDirectorsText = document.getElementById('dialogDirectorsText');
    const dialogCast = document.getElementById('dialogCast');
    const dialogCastText = document.getElementById('dialogCastText');
    
    // Set title with year if available
    if (year && year !== '') {
        dialogTitle.textContent = `${title} (${year})`;
    } else {
        dialogTitle.textContent = title;
    }
    
    // Set poster image if available
    if (posterUrl && posterUrl !== '' && posterUrl !== 'None') {
        dialogPosterImg.src = posterUrl;
        dialogPoster.style.display = 'block';
    } else {
        dialogPoster.style.display = 'none';
    }
    
    // Set TMDB rating badge if available
    if (dialogTmdbBadge && dialogTmdbRatingElement) {
        if (tmdbRating && tmdbRating !== '' && tmdbRating !== 'None' && parseFloat(tmdbRating) > 0) {
            dialogTmdbRatingElement.textContent = parseFloat(tmdbRating).toFixed(1);
            dialogTmdbBadge.style.display = 'flex';
        } else {
            dialogTmdbBadge.style.display = 'none';
        }
    }
    
    // Set plot if available, otherwise show fallback text
    if (plot && plot !== '' && plot !== 'None') {
        dialogPlotText.textContent = plot;
        dialogPlot.style.display = 'flex';
    } else {
        dialogPlotText.textContent = t('dialog_no_info');
        dialogPlot.style.display = 'flex';
    }
    
    // Set directors if available
    if (directors && directors !== '') {
        dialogDirectorsText.textContent = directors;
        dialogDirectors.style.display = 'flex';
    } else {
        dialogDirectors.style.display = 'none';
    }
    
    // Set cast if available (with "..." to indicate more actors)
    if (cast && cast !== '') {
        dialogCastText.textContent = cast + ' ...';
        dialogCast.style.display = 'flex';
    } else {
        dialogCast.style.display = 'none';
    }
    
    // Set duration
    dialogDuration.textContent = formatDuration(duration);
    
    // Set file size
    if (fileSize !== null && fileSize !== undefined && fileSize >= 0) {
        dialogFileSize.textContent = formatFileSize(fileSize);
    } else {
        dialogFileSize.textContent = 'Unknown';
    }
    
    // Set video bitrate
    if (videoBitrate && videoBitrate > 0) {
        dialogVideoBitrate.textContent = `${videoBitrate} kbit/s`;
    } else {
        dialogVideoBitrate.textContent = 'Unknown';
    }
    
    // Set audio bitrate
    if (audioBitrate && audioBitrate > 0) {
        dialogAudioBitrate.textContent = `${audioBitrate} kbit/s`;
    } else {
        dialogAudioBitrate.textContent = 'Unknown';
    }
    
    // Set up links
    dialogTmdbLink.classList.remove(...dialogTmdbLink.classList);
    dialogTmdbLink.classList.add('dialog-link', 'tmdb');
    dialogTrailerLink.classList.remove(...dialogTrailerLink.classList);
    dialogTrailerLink.classList.add('dialog-link', 'youtube');

    if (tmdbId && tmdbId !== 'None') {
        // TMDb link - direct to movie page
        dialogTmdbLink.href = `https://www.themoviedb.org/movie/${tmdbId}`;
        dialogTmdbLink.style.display = 'inline-block';
        
        // Set up YouTube trailer link
        if (title && title !== '') {
            const searchQuery = year && year !== '' ?
                `${title} (${year}) - Trailer` :
                `${title} - Trailer`;
            const youtubeUrl = `https://www.youtube.com/results?search_query=${encodeURIComponent(searchQuery)}`;
            dialogTrailerLink.href = youtubeUrl;
            dialogTrailerLink.style.display = 'inline-block';

            if (dialogTrailer && dialogTrailer.style) dialogTrailer.style.display = '';
        } else {
            dialogTrailerLink.style.display = 'none';
        }
        
        // Show links container
        if (dialogLinksContainer) dialogLinksContainer.style.display = '';
    } else {
        // Hide links if no TMDb ID
        dialogTmdbLink.style.display = 'none';
        dialogTrailerLink.style.display = 'none';
        
        // Hide entire links container
        if (dialogLinksContainer) dialogLinksContainer.style.display = 'none';
    }
    
    // Show dialog
    overlay.classList.add('active');
    document.body.style.overflow = 'hidden';
    
    // Apply translations
    applyTranslations();
    
    // Setup swipe gesture for mobile (only once)
    if (!swipeListenersAttached) {
        setupSwipeToClose();
    }
}

function showMediaDialogFromData(element) {
    // Extract data attributes safely from the clicked element
    const title = element.getAttribute('data-title') || '';
    const year = element.getAttribute('data-year') || '';
    const duration = parseFloat(element.getAttribute('data-duration')) || null;
    const videoBitrate = parseInt(element.getAttribute('data-video-bitrate')) || null;
    const audioBitrate = parseInt(element.getAttribute('data-audio-bitrate')) || null;
    const fileSize = parseInt(element.getAttribute('data-file-size')) || null;
    const posterUrl = element.getAttribute('data-poster-url') || '';
    const tmdbId = element.getAttribute('data-tmdb-id') || '';
    const tmdbRating = element.getAttribute('data-tmdb-rating') || '';
    const plot = element.getAttribute('data-plot') || '';
    const directors = element.getAttribute('data-directors') || '';
    const cast = element.getAttribute('data-cast') || '';
    
    showMediaDialog(title, year, duration, videoBitrate, audioBitrate, fileSize, posterUrl, tmdbId, plot, directors, cast, tmdbRating);
}

function closeMediaDialog(event) {
    if (event) {
        event.stopPropagation();
    }
    
    const overlay = document.getElementById('mediaDialogOverlay');
    overlay.classList.remove('active');
    document.body.style.overflow = '';
}

// Swipe gesture handling for mobile
let touchStartX = 0;
let touchStartY = 0;
let touchEndX = 0;
let touchEndY = 0;
let swipeListenersAttached = false;

function setupSwipeToClose() {
    const dialog = document.querySelector('.media-dialog');
    
    if (!dialog || swipeListenersAttached) return;
    
    dialog.addEventListener('touchstart', function(e) {
        touchStartX = e.changedTouches[0].screenX;
        touchStartY = e.changedTouches[0].screenY;
    }, { passive: true });
    
    dialog.addEventListener('touchend', function(e) {
        touchEndX = e.changedTouches[0].screenX;
        touchEndY = e.changedTouches[0].screenY;
        handleSwipe();
    }, { passive: true });
    
    swipeListenersAttached = true;
}

function handleSwipe() {
    const swipeThreshold = 100;
    const horizontalSwipe = Math.abs(touchEndX - touchStartX);
    const verticalSwipe = Math.abs(touchEndY - touchStartY);
    
    // Only consider horizontal swipes (left or right)
    if (horizontalSwipe > swipeThreshold && horizontalSwipe > verticalSwipe) {
        closeMediaDialog();
    }
}
