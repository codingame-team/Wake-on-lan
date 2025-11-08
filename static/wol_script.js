function showAlert(message, type) {
    const container = document.getElementById('alert-container');
    const alert = document.createElement('div');
    alert.className = 'alert ' + type;
    alert.textContent = message;
    container.innerHTML = '';
    container.appendChild(alert);
    
    setTimeout(function() {
        alert.style.opacity = '0';
        alert.style.transition = 'opacity 0.5s';
        setTimeout(function() { 
            if (alert.parentNode) {
                container.removeChild(alert);
            }
        }, 500);
    }, 5000);
}

function updateStatus(machineId, status, text) {
    const statusEl = document.getElementById('status-' + machineId);
    if (statusEl) {
        statusEl.className = 'status ' + status;
        statusEl.textContent = text;
    }
}

async function checkStatus(machineId, ip) {
    try {
        const response = await fetch('/api/ping/' + ip);
        const data = await response.json();
        
        if (data.online) {
            updateStatus(machineId, 'online', 'En ligne');
        } else {
            updateStatus(machineId, 'offline', 'Hors ligne');
        }
    } catch (error) {
        updateStatus(machineId, 'offline', 'Hors ligne');
    }
}

async function wakeUp(machineId, mac, ip) {
    const btn = document.getElementById('btn-' + machineId);
    btn.disabled = true;
    btn.innerHTML = '<span class="loading"></span>Envoi du paquet WOL...';
    updateStatus(machineId, 'checking', 'Envoi WOL...');
    
    try {
        const response = await fetch('/api/wol', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ mac: mac, ip: ip })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showAlert('Paquet WOL envoye avec succes!', 'success');
            updateStatus(machineId, 'checking', 'Demarrage...');
            
            // Attendre et verifier le statut
            setTimeout(function() {
                btn.innerHTML = 'Attente du demarrage...';
                waitForOnline(machineId, ip, btn);
            }, 2000);
        } else {
            showAlert('Erreur: ' + (data.error || 'Echec de envoi'), 'error');
            btn.disabled = false;
            btn.innerHTML = 'Reveiller';
            updateStatus(machineId, 'offline', 'Echec');
        }
    } catch (error) {
        showAlert('Erreur reseau: ' + error.message, 'error');
        btn.disabled = false;
        btn.innerHTML = 'Reveiller';
        updateStatus(machineId, 'offline', 'Erreur');
    }
}

async function waitForOnline(machineId, ip, btn, attempt) {
    if (typeof attempt === 'undefined') attempt = 0;
    const maxAttempts = 60; // 60 secondes
    
    if (attempt >= maxAttempts) {
        showAlert('Timeout: La machine na pas demarre apres 60 secondes', 'warning');
        btn.disabled = false;
        btn.innerHTML = 'Reveiller';
        updateStatus(machineId, 'offline', 'Timeout');
        return;
    }
    
    try {
        const response = await fetch('/api/ping/' + ip);
        const data = await response.json();
        
        if (data.online) {
            showAlert('Machine demarree et accessible!', 'success');
            btn.disabled = false;
            btn.innerHTML = 'Reveiller';
            updateStatus(machineId, 'online', 'En ligne');
            return;
        }
    } catch (error) {
        // Continue a attendre
    }
    
    // Reessayer apres 1 seconde
    setTimeout(function() {
        waitForOnline(machineId, ip, btn, attempt + 1);
    }, 1000);
}
