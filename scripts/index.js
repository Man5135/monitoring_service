document.addEventListener('DOMContentLoaded', function() {
    const startBtn = document.getElementById('start-equipment-btn');
    const stopBtn = document.getElementById('stop-equipment-btn');
    const statusDiv = document.getElementById('arduino-status');
    let isProcessing = false;
    let updateInterval = null;

    // Функция форматирования московского времени с +3 часами
    function formatMoscowTime(dateString) {
        if (!dateString) return '';
        const date = new Date(dateString);
        date.setHours(date.getHours() + 3); // Добавляем 3 часа
        return date.toLocaleString('ru-RU', {
            timeZone: 'Europe/Moscow',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: false
        });
    }

    // Инициализация графика
    const ctx = document.getElementById('sensor-chart')?.getContext('2d');
    let chart;
    
    if (ctx) {
        chart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: ['Температура', 'Давление', 'Вибрация', 'Скорость', 'Нагрузка'],
                datasets: [{
                    label: 'Показатели датчиков',
                    data: [0, 0, 0, 0, 0],
                    backgroundColor: 'rgba(75, 192, 192, 0.2)',
                    borderColor: 'rgba(75, 192, 192, 1)',
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                scales: {
                    y: { beginAtZero: false }
                },
                animation: {
                    duration: 1000
                }
            }
        });
    }

    // Функция обновления данных
    function updateData() {
        fetch('/get_equipment_data')
            .then(response => response.json())
            .then(data => {
                if (!data || Object.keys(data).length === 0) return;
                
                // Обновление показаний
                const elements = {
                    'temperature': `${data.temperature?.toFixed(1) || '0'} °C`,
                    'pressure': `${data.pressure?.toFixed(1) || '0'} бар`,
                    'vibration': `${data.vibration?.toFixed(1) || '0'} мм/с`,
                    'spindle-speed': `${Math.round(data.spindle_speed) || '0'} об/мин`,
                    'load': `${Math.round(data.load) || '0'}%`
                };
                
                for (const [id, value] of Object.entries(elements)) {
                    const el = document.getElementById(id);
                    if (el) el.textContent = value;
                }

                // Обновление графика
                if (chart) {
                    chart.data.datasets[0].data = [
                        data.temperature || 0,
                        data.pressure || 0,
                        data.vibration || 0,
                        data.spindle_speed || 0,
                        data.load || 0
                    ];
                    chart.update();
                }

                // Обновление состояния кнопок
                if (startBtn && stopBtn) {
                    startBtn.disabled = isProcessing || data.is_running;
                    stopBtn.disabled = isProcessing || !data.is_running;
                }

                // Обновление статуса
                if (statusDiv) {
                    if (!data.arduino_connected) {
                        statusDiv.textContent = "Станок не подключен";
                        statusDiv.className = 'status-message error';
                    } else if (data.is_running) {
                        statusDiv.textContent = "Станок работает";
                        statusDiv.className = 'status-message success';
                    } else {
                        statusDiv.textContent = "Станок готов к запуску";
                        statusDiv.className = 'status-message info';
                    }
                }

                // Показ предупреждений
                if (data.alerts && data.alerts.length > 0) {
                    data.alerts.forEach(alert => {
                        showAlert(alert);
                    });
                }
            })
            .catch(error => {
                console.error("Ошибка получения данных:", error);
            });
    }

    // Функция для показа предупреждений
    function showAlert(message) {
        const alertDiv = document.createElement('div');
        alertDiv.className = 'alert alert-danger';
        alertDiv.textContent = message;
        document.body.prepend(alertDiv);
        
        setTimeout(() => {
            alertDiv.remove();
        }, 5000);
    }

    // Функция запуска станка
    async function startEquipment() {
        if (isProcessing) return;
        isProcessing = true;
        
        if (startBtn) startBtn.disabled = true;
        if (statusDiv) {
            statusDiv.textContent = "Запускаем станок...";
            statusDiv.className = 'status-message info';
        }

        try {
            const response = await fetch('/start_equipment', { method: 'POST' });
            const data = await response.json();
            
            if (data.status === 'success') {
                if (!updateInterval) {
                    updateInterval = setInterval(updateData, 2000);
                }
                updateData();
            } else {
                if (statusDiv) {
                    statusDiv.textContent = data.message || "Ошибка запуска";
                    statusDiv.className = 'status-message error';
                }
            }
        } catch (error) {
            console.error("Ошибка:", error);
            if (statusDiv) {
                statusDiv.textContent = "Ошибка соединения";
                statusDiv.className = 'status-message error';
            }
        } finally {
            isProcessing = false;
            updateData();
        }
    }

    // Функция остановки станка
    async function stopEquipment() {
        if (isProcessing) return;
        isProcessing = true;
        
        if (stopBtn) stopBtn.disabled = true;
        if (statusDiv) {
            statusDiv.textContent = "Останавливаем станок...";
            statusDiv.className = 'status-message info';
        }

        try {
            const response = await fetch('/stop_equipment', { method: 'POST' });
            const data = await response.json();
            
            if (data.status !== 'success' && statusDiv) {
                statusDiv.textContent = data.message || "Ошибка остановки";
                statusDiv.className = 'status-message error';
            }
        } catch (error) {
            console.error("Ошибка:", error);
            if (statusDiv) {
                statusDiv.textContent = "Ошибка соединения";
                statusDiv.className = 'status-message error';
            }
        } finally {
            isProcessing = false;
            updateData();
        }
    }

    // Назначение обработчиков
    startBtn?.addEventListener('click', startEquipment);
    stopBtn?.addEventListener('click', stopEquipment);

    // Автоматическое обновление данных каждые 3 секунды
    updateData();
    setInterval(updateData, 3000);
});