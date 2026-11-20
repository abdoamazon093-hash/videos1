document.addEventListener('DOMContentLoaded', () => {
    const healthStatusEl = document.getElementById('health-status');
    const uptimeValEl = document.getElementById('uptime-val');
    const cacheCountEl = document.getElementById('cache-count');
    const appPortEl = document.getElementById('app-port');
    const cacheListEl = document.getElementById('cache-list');
    const cacheForm = document.getElementById('cache-form');

    // Fetch Health Stats
    async function loadHealth() {
        try {
            const res = await fetch('/api/health');
            if (!res.ok) throw new Error('Health check failed');
            const data = await res.json();
            
            healthStatusEl.textContent = data.status === 'healthy' ? 'نشط ويعمل بنجاح (Healthy)' : 'تنبيه (Degraded)';
            healthStatusEl.className = data.status === 'healthy' ? 'value ok' : 'value font-mono';
            
            const mins = Math.floor(data.uptime_seconds / 60);
            const secs = data.uptime_seconds % 60;
            uptimeValEl.textContent = `${mins} دقيقة و ${secs} ثانية`;
            
            if (data.database && typeof data.database.total_items !== 'undefined') {
                cacheCountEl.textContent = data.database.total_items;
            }
        } catch (err) {
            healthStatusEl.textContent = 'غير متصل';
            healthStatusEl.style.color = '#ef4444';
        }
    }

    // Fetch App Info
    async function loadInfo() {
        try {
            const res = await fetch('/api/info');
            if (res.ok) {
                const info = await res.json();
                if (info.port) {
                    appPortEl.textContent = info.port;
                }
            }
        } catch (e) {
            console.error('Error fetching info', e);
        }
    }

    // Load Cache Items
    async function loadCache() {
        try {
            const res = await fetch('/api/cache');
            if (!res.ok) return;
            const items = await res.json();
            
            cacheCountEl.textContent = items.length;
            if (items.length === 0) {
                cacheListEl.innerHTML = '<p class="empty-state">لا توجد عناصر في الكاش بعد.</p>';
                return;
            }

            cacheListEl.innerHTML = '';
            items.forEach(item => {
                const card = document.createElement('div');
                card.className = 'cache-card';
                card.innerHTML = `
                    <div class="cache-meta">
                        <span class="cache-key-name">${escapeHtml(item.key)}</span>
                        <span class="cache-val-preview">${escapeHtml(item.value)}</span>
                    </div>
                    <button class="btn-danger-sm" data-key="${escapeHtml(item.key)}">حذف</button>
                `;
                card.querySelector('button').addEventListener('click', () => deleteItem(item.key));
                cacheListEl.appendChild(card);
            });
        } catch (err) {
            console.error('Error loading cache', err);
        }
    }

    // Delete Cache Item
    async function deleteItem(key) {
        if (!confirm(`هل أنت متأكد من حذف المفتاح: ${key}؟`)) return;
        try {
            const res = await fetch(`/api/cache/${encodeURIComponent(key)}`, {
                method: 'DELETE'
            });
            if (res.ok) {
                loadCache();
                loadHealth();
            }
        } catch (err) {
            alert('حدث خطأ أثناء الحذف');
        }
    }

    // Add Cache Item
    cacheForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const key = document.getElementById('cache-key').value.trim();
        const value = document.getElementById('cache-val').value.trim();
        const ttlInput = document.getElementById('cache-ttl').value.trim();
        const ttl_seconds = ttlInput ? parseInt(ttlInput, 10) : null;

        if (!key || !value) return;

        try {
            const res = await fetch('/api/cache', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ key, value, ttl_seconds })
            });

            if (res.ok) {
                cacheForm.reset();
                loadCache();
                loadHealth();
            } else {
                const err = await res.json();
                alert('فشل الحفظ: ' + (err.detail || 'حدث خطأ'));
            }
        } catch (err) {
            alert('تعذر الاتصال بالخادم.');
        }
    });

    function escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    // Initial Load & Polling
    loadInfo();
    loadHealth();
    loadCache();
    setInterval(loadHealth, 5000);
});
