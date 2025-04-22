document.addEventListener('DOMContentLoaded', function() {
    function formatMoscowTime(dateString) {
        if (!dateString) return 'Нет данных';
        try {
            const date = new Date(dateString);
            date.setHours(date.getHours() + 3);
            return date.toLocaleString('ru-RU', {
                timeZone: 'Europe/Moscow',
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
                hour12: false
            });
        } catch (e) {
            console.error('Ошибка форматирования времени:', e);
            return dateString;
        }
    }

    // Инициализация графика
    const ctx = document.getElementById('equipment-chart')?.getContext('2d');
    if (ctx) {
        const chart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: ['Температура', 'Давление', 'Вибрация', 'Скорость', 'Нагрузка'],
                datasets: [{
                    label: 'Текущие показатели',
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
                plugins: {
                    legend: {
                        position: 'top',
                    },
                    title: {
                        display: true,
                        text: 'Показатели станка'
                    }
                }
            }
        });

        // Функция обновления данных
        function updateAdminData() {
            fetch('/admin/update_data')
                .then(response => response.json())
                .then(data => {
                    if (data && data.temperature !== undefined) {
                        // Обновляем график
                        chart.data.datasets[0].data = [
                            data.temperature || 0,
                            data.pressure || 0,
                            data.vibration || 0,
                            data.spindle_speed || 0,
                            data.load || 0
                        ];
                        chart.update();

                        // Обновляем текстовые значения
                        document.getElementById('temperature-value').textContent = 
                            `${data.temperature?.toFixed(1) || '0'} °C` + 
                            (data.temperature > 80 ? ' (Высокая!)' : '');
                        
                        document.getElementById('pressure-value').textContent = 
                            `${data.pressure?.toFixed(1) || '0'} бар` + 
                            (data.pressure > 2.0 ? ' (Высокое!)' : '');
                        
                        document.getElementById('vibration-value').textContent = 
                            `${data.vibration?.toFixed(1) || '0'} мм/с` + 
                            (data.vibration > 1.5 ? ' (Сильная!)' : '');
                        
                        document.getElementById('speed-value').textContent = 
                            `${Math.round(data.spindle_speed) || '0'} об/мин`;
                        
                        document.getElementById('load-value').textContent = 
                            `${Math.round(data.load) || '0'}%`;
                        
                        document.getElementById('status-value').textContent = 
                            data.is_running ? "Работает" : "Остановлен";
                        
                        // Обновляем время с учетом московского часового пояса
                        document.getElementById('start-time-value').textContent = 
                            formatMoscowTime(data.start_time);
                        document.getElementById('stop-time-value').textContent = 
                            formatMoscowTime(data.stop_time);
                        document.getElementById('last-updated-value').textContent = 
                            formatMoscowTime(data.last_updated);
                        
                        // Обновляем время работы
                        const runtimeMinutes = (data.total_runtime / 1000 / 60).toFixed(1);
                        document.getElementById('runtime-value').textContent = 
                            `${runtimeMinutes} минут`;
                    }
                })
                .catch(error => console.error('Error updating data:', error));
        }

        // Обновляем данные каждые 2 секунды
        updateAdminData();
        setInterval(updateAdminData, 2000);
    }

    // Обработчик кнопки создания отчета
    document.getElementById('generate-report-btn')?.addEventListener('click', function() {
        const timestamp = new Date().getTime();
        window.location.href = `/generate_report?t=${timestamp}`;
    });

    // Обработчик кнопки очистки логов
    document.getElementById('clear-logs-btn')?.addEventListener('click', async function() {
        const button = this;
        if (confirm('Вы уверены, что хотите удалить все записи логов? Это действие нельзя отменить.')) {
            button.disabled = true;
            button.textContent = 'Очистка...';
            
            try {
                const response = await fetch('/admin/clear_logs', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    }
                });
                
                const data = await response.json();
                
                if (data.status === 'success') {
                    // Обновляем таблицу
                    const tableBody = document.querySelector('.events-table tbody');
                    if (tableBody) {
                        // Сохраняем заголовки
                        const headerRow = tableBody.querySelector('tr:first-child');
                        tableBody.innerHTML = '';
                        if (headerRow) tableBody.appendChild(headerRow);
                        
                        // Добавляем сообщение об успехе
                        const messageRow = document.createElement('tr');
                        messageRow.innerHTML = `
                            <td colspan="8" style="text-align: center; padding: 20px; color: green;">
                                Логи успешно очищены (удалено ${data.count} записей)
                            </td>
                        `;
                        tableBody.appendChild(messageRow);
                    }
                    
                    // Показываем всплывающее уведомление
                    showAlert('Логи успешно очищены', 'success');
                } else {
                    throw new Error(data.message || 'Неизвестная ошибка');
                }
            } catch (error) {
                console.error('Error:', error);
                showAlert('Ошибка при удалении логов: ' + error.message, 'error');
            } finally {
                button.disabled = false;
                button.textContent = 'Очистить логи';
            }
        }
    });

    // Функция показа уведомлений
    function showAlert(message, type = 'error') {
        const alertsContainer = document.getElementById('alerts-container');
        if (!alertsContainer) return;
        
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert-popup ${type}`;
        alertDiv.textContent = message;
        alertsContainer.appendChild(alertDiv);
        
        setTimeout(() => {
            alertDiv.remove();
        }, 5000);
    }

    // Проверка предупреждений
    function checkForAlerts() {
        fetch('/get_equipment_data')
            .then(response => response.json())
            .then(data => {
                if (data.alerts && data.alerts.length > 0) {
                    data.alerts.forEach(alert => {
                        showAlert(alert, 'error');
                    });
                }
            });
    }

    setInterval(checkForAlerts, 5000);
});
document.addEventListener('DOMContentLoaded', function() {
    // Обработчик для кнопок удаления
    document.querySelectorAll('.delete-btn').forEach(btn => {
        btn.addEventListener('click', function(e) {
            const row = this.closest('tr');
            const role = row.querySelector('td:nth-child(3)').textContent;
            const adminCount = document.querySelectorAll('tr td:nth-child(3)').length;
            
            if (role === 'admin' && adminCount <= 1) {
                e.preventDefault();
                showAlert('Нельзя удалить последнего администратора!', 'error');
            }
        });
    });
});