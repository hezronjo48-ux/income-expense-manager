// ============================================================
// INCOME & EXPENSE MANAGEMENT SYSTEM - MAIN JAVASCRIPT
// ============================================================

// PWA Install Prompt
let deferredPrompt = null;
let installButton = null;

window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredPrompt = e;
    showInstallButton();
});

window.addEventListener('appinstalled', () => {
    console.log('PWA installed');
    hideInstallButton();
    deferredPrompt = null;
});

function showInstallButton() {
    if (installButton) return;
    
    installButton = document.createElement('button');
    installButton.className = 'btn btn-primary pwa-install-btn';
    installButton.style.cssText = 'position:fixed;bottom:24px;right:24px;z-index:1000;box-shadow:0 4px 20px rgba(14,165,233,0.3);animation:rise 0.3s ease-out;';
    installButton.innerHTML = '<i class="fas fa-download"></i><span>Install App</span>';
    installButton.onclick = installPWA;
    document.body.appendChild(installButton);
}

function hideInstallButton() {
    if (installButton) {
        installButton.remove();
        installButton = null;
    }
}

async function installPWA() {
    if (!deferredPrompt) return;
    
    hideInstallButton();
    deferredPrompt.prompt();
    
    const { outcome } = await deferredPrompt.userChoice;
    console.log(`PWA install ${outcome}`);
    deferredPrompt = null;
}

// Register Service Worker
if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/static/sw.js?v=' + Date.now())
            .then(reg => {
                console.log('SW registered:', reg.scope);
                
                // Check for updates
                reg.addEventListener('updatefound', () => {
                    const newWorker = reg.installing;
                    newWorker.addEventListener('statechange', () => {
                        if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
                            showUpdateAvailable();
                        }
                    });
                });
            })
            .catch(err => console.log('SW registration failed:', err));
    });
}

function showUpdateAvailable() {
    const banner = document.createElement('div');
    banner.className = 'flash-message flash-info';
    banner.style.cssText = 'position:fixed;top:20px;left:50%;transform:translateX(-50%);z-index:2000;max-width:90%;';
    banner.innerHTML = `
        <span><i class="fas fa-sync"></i> New version available!</span>
        <button class="btn btn-sm btn-primary" onclick="location.reload()"><i class="fas fa-redo"></i> Refresh</button>
        <button class="btn btn-sm btn-secondary" onclick="this.parentElement.remove()"><i class="fas fa-times"></i></button>
    `;
    document.body.appendChild(banner);
}

// Auto-hide flash messages after 5 seconds
document.addEventListener('DOMContentLoaded', function() {
    var flashes = document.querySelectorAll('.flash-message');
    flashes.forEach(function(flash) {
        setTimeout(function() {
            if (flash.parentElement) {
                flash.style.transition = 'opacity 0.3s ease';
                flash.style.opacity = '0';
                setTimeout(function() { if (flash.parentElement) flash.remove(); }, 300);
            }
        }, 5000);
    });
});

// Modal functions
function openModal(title, contentHtml) {
    document.getElementById('modalTitle').textContent = title;
    document.getElementById('modalBody').innerHTML = contentHtml;
    document.getElementById('modalOverlay').style.display = 'block';
    document.getElementById('modalBox').style.display = 'block';
    document.body.style.overflow = 'hidden';
}

function closeModal() {
    document.getElementById('modalOverlay').style.display = 'none';
    document.getElementById('modalBox').style.display = 'none';
    document.body.style.overflow = '';
}

// Close modal with Escape key
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') closeModal();
});

// Confirm dialog helper
function confirmAction(message) {
    return confirm(message);
}

// Format number as currency
function formatCurrency(amount, symbol) {
    symbol = symbol || '$';
    return symbol + parseFloat(amount).toFixed(2);
}

// Toggle monitoring submenu
function toggleMonitoring(el) {
    var sub = document.getElementById('monitoringSubmenu');
    var arrow = document.getElementById('monitoringArrow');
    if (sub) {
        sub.classList.toggle('open');
        if (arrow) arrow.classList.toggle('open');
    }
}

// Mobile sidebar toggle
function toggleSidebar() {
    document.getElementById('sidebar').classList.toggle('open');
    document.getElementById('sidebarOverlay').classList.toggle('open');
    document.body.style.overflow = document.body.style.overflow === 'hidden' ? '' : 'hidden';
}

function closeSidebar() {
    document.getElementById('sidebar').classList.remove('open');
    document.getElementById('sidebarOverlay').classList.remove('open');
    document.body.style.overflow = '';
}

// Close sidebar when navigating on mobile
document.addEventListener('DOMContentLoaded', function() {
    var sidebarLinks = document.querySelectorAll('.sidebar-nav a');
    sidebarLinks.forEach(function(link) {
        link.addEventListener('click', function() {
            if (window.innerWidth <= 700) {
                closeSidebar();
            }
        });
    });
});

// Poll unread notification count every 30s (only on pages with badge)
document.addEventListener('DOMContentLoaded', function() {
    var badge = document.getElementById('notifBadge');
    if (!badge) return;
    function pollNotifs() {
        fetch('/monitoring/notifications/count').then(function(r) { return r.json(); }).then(function(d) {
            if (d.count > 0) {
                badge.textContent = d.count > 99 ? '99+' : d.count;
                badge.style.display = 'inline';
            } else {
                badge.style.display = 'none';
            }
        }).catch(function() {});
    }
    pollNotifs();
    setInterval(pollNotifs, 30000);
});

// Offline detection
window.addEventListener('online', () => {
    console.log('Back online');
    document.body.classList.remove('offline');
});

window.addEventListener('offline', () => {
    console.log('Gone offline');
    document.body.classList.add('offline');
    
    const banner = document.createElement('div');
    banner.className = 'flash-message flash-warning';
    banner.id = 'offline-banner';
    banner.style.cssText = 'position:fixed;top:20px;left:50%;transform:translateX(-50%);z-index:2000;max-width:90%;';
    banner.innerHTML = '<span><i class="fas fa-wifi-slash"></i> You are offline. Changes will sync when reconnected.</span>';
    document.body.appendChild(banner);
});

// Remove offline banner when back online
window.addEventListener('online', () => {
    const banner = document.getElementById('offline-banner');
    if (banner) banner.remove();
});
