import paho.mqtt.client as mqtt
import time
import random
import json
import tkinter as tk
from tkinter import messagebox, ttk, scrolledtext
import requests
import threading
import datetime

# Настройки MQTT
BROKER = "localhost"
PORT = 1883
CLIENT_ID = "SimulatorClient"
TOPIC_PREFIX = "agrodata/sensor/"

# Настройки API сервера
SERVER_URL = "http://localhost:8081"
USERNAME = "user"
PASSWORD = "password"

# Список активных датчиков
active_sensors = {}
running = False  # Флаг для управления отправкой
threads = []  # Список активных потоков

# Подключение к MQTT
client = mqtt.Client(client_id=CLIENT_ID, callback_api_version=mqtt.CallbackAPIVersion.VERSION2)


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print("Connected to MQTT broker")
    else:
        print(f"Failed to connect: {reason_code}")


client.on_connect = on_connect


# Функции для работы с API
def fetch_fields():
    try:
        response = requests.get(f"{SERVER_URL}/fields")
        if response.status_code == 200:
            return response.json()
        else:
            messagebox.showerror("Ошибка", f"Не удалось загрузить список полей: {response.status_code}")
            return []
    except Exception as e:
        messagebox.showerror("Ошибка", f"Ошибка при загрузке полей: {e}")
        return []


def fetch_sensors_for_field(field_id):
    try:
        response = requests.get(f"{SERVER_URL}/sensors/field/{field_id}")
        if response.status_code == 200:
            return response.json()
        else:
            messagebox.showerror("Ошибка", f"Не удалось загрузить датчики: {response.status_code}")
            return []
    except Exception as e:
        messagebox.showerror("Ошибка", f"Ошибка при загрузке датчиков: {e}")
        return []


# Функция для создания ISO timestamp с миллисекундами
def get_iso_timestamp():
    """
    Создает строку с датой в формате ISO 8601 с микросекундами
    Формат: 'yyyy-MM-dd'T'HH:mm:ss.SSSSSS'Z'' (UTC с микросекундами)
    """
    # Используем UTC время с полной точностью микросекунд
    now = datetime.datetime.now(datetime.timezone.utc)
    # Формат с полными микросекундами и Z в конце (означает UTC)
    return now.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-0] + 'Z'


def get_iso_timestamp():
    """
    Создает строку с датой в формате ISO 8601, совместимом с сервером.
    Формат: 'yyyy-MM-dd'T'HH:mm:ss.SSS'Z'' (UTC)
    """
    # Используем UTC время
    now = datetime.datetime.now(datetime.timezone.utc)
    # Формат с Z в конце (означает UTC)
    return now.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + 'Z'


# Функция симуляции данных
def simulate_sensor_data(sensor_name, field_id, num_sends, total_time, unit, min_value, max_value, repeat,
                         accuracy_class, extra_params, log_text):
    global running
    if num_sends <= 0 or total_time <= 0:
        messagebox.showerror("Ошибка", "Количество отправок и время должны быть больше 0")
        return

    # Проверяем корректность диапазона значений
    if min_value >= max_value:
        messagebox.showerror("Ошибка", "Минимальное значение должно быть меньше максимального")
        return

    # Правильный расчет интервала между отправками
    if num_sends > 1:
        interval = total_time / (num_sends - 1)
    else:
        interval = 0

    # Проверяем частоту отправки - если слишком высокая, логируем предупреждение
    frequency = num_sends / total_time if total_time > 0 else float('inf')
    if frequency > 50:  # Более 50 сообщений в секунду
        log_text.insert(tk.END,
                        f"ВНИМАНИЕ: Высокая частота отправки ({frequency:.1f} сообщ/сек). " +
                        f"Используется режим пакетной отправки.\n")
        log_text.see(tk.END)

    cycle_count = 0  # Счетчик циклов для логирования
    total_msg_count = 0  # Счетчик всех отправленных сообщений

    try:
        # Попытка установить соединение с MQTT брокером
        if not client.is_connected():
            client.connect(BROKER, PORT)
            client.loop_start()
            log_text.insert(tk.END, "MQTT соединение установлено\n")
            log_text.see(tk.END)
    except Exception as e:
        log_text.insert(tk.END, f"Ошибка подключения к MQTT брокеру: {e}\n")
        log_text.see(tk.END)
        del active_sensors[sensor_name]
        return

    while running and sensor_name in active_sensors:
        cycle_count += 1
        log_text.insert(tk.END, f"Цикл {cycle_count} для {sensor_name}\n")
        log_text.see(tk.END)

        # Определяем базовое время для этого цикла отправок
        base_time = datetime.datetime.now(datetime.timezone.utc)

        # Скорость вывода в лог
        log_frequency = max(1, min(num_sends // 20, 50))  # Логируем не более 50 сообщений, минимум 1

        # Генерируем все сообщения заранее для оптимизации
        messages = []
        for i in range(num_sends):
            value = round(random.uniform(min_value, max_value), 2)

            # Создаем timestamp с точностью до миллисекунд
            # При пакетной отправке добавляем i*10 миллисекунд к базовому времени
            # для обеспечения последовательных временных меток
            if frequency > 50:  # При высокой частоте обеспечиваем разные timestamps
                ts_date = base_time + datetime.timedelta(milliseconds=i * 10)
            else:  # При низкой частоте используем текущее время
                ts_date = datetime.datetime.now(datetime.timezone.utc)

            timestamp = ts_date.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + 'Z'

            # Подготавливаем extraParams
            message_extra_params = None
            if extra_params:
                try:
                    message_extra_params = json.loads(extra_params)
                except json.JSONDecodeError:
                    log_text.insert(tk.END, f"Ошибка: Некорректный формат JSON в доп. параметрах\n")
                    log_text.see(tk.END)

            # Формируем данные сообщения
            payload_dict = {
                "sensorName": sensor_name,
                "value": value,
                "fieldId": field_id,
                "unit": unit,
                "timestamp": timestamp
            }

            # Добавляем класс точности, если указан
            if accuracy_class:
                payload_dict["accuracyClass"] = accuracy_class

            # Добавляем extraParams, если есть
            if message_extra_params:
                payload_dict["extraParams"] = message_extra_params

            messages.append((i, timestamp, json.dumps(payload_dict)))

        # Фактическое начало отправки
        start_time = time.time()

        # Отправляем сообщения с соблюдением интервала
        for i, timestamp, payload in messages:
            if not running or sensor_name not in active_sensors:
                break

            # Расчет целевого времени отправки
            target_time = start_time + i * interval if i > 0 else start_time

            # Проверяем подключение к MQTT брокеру
            if not client.is_connected():
                try:
                    client.reconnect()
                    log_text.insert(tk.END, "Переподключение к MQTT брокеру\n")
                    log_text.see(tk.END)
                except Exception as e:
                    log_text.insert(tk.END, f"Ошибка переподключения к MQTT брокеру: {e}\n")
                    log_text.see(tk.END)
                    break

            # Публикуем сообщение с QoS 1 для гарантии доставки
            result = client.publish(f"{TOPIC_PREFIX}{sensor_name}", payload, qos=1)

            # Логируем результат (не для каждого сообщения при высокой частоте)
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                if i % log_frequency == 0 or i == num_sends - 1:
                    log_text.insert(tk.END,
                                    f"Отправка {i + 1}/{num_sends} успешна ({timestamp})\n")
                    log_text.see(tk.END)
            else:
                log_text.insert(tk.END, f"Ошибка отправки: {result.rc}\n")
                log_text.see(tk.END)

            # Ждем до следующего целевого времени отправки
            if i < num_sends - 1 and interval > 0:
                current_time = time.time()
                wait_time = max(0, target_time + interval - current_time)

                # Короткие ожидания (менее 10 мс) пропускаем при высокой частоте
                if wait_time > 0.01 or frequency < 50:
                    wait_start = time.time()
                    while time.time() - wait_start < wait_time:
                        if not running or sensor_name not in active_sensors:
                            break
                        time.sleep(min(0.01, wait_time / 2))

        # Увеличиваем общий счетчик сообщений
        total_msg_count += num_sends

        # Если повторение включено, ждем перед следующим циклом
        if repeat and running and sensor_name in active_sensors:
            log_text.insert(tk.END, f"Цикл завершен. Всего отправлено: {total_msg_count}\n")
            log_text.see(tk.END)

            # Пауза между циклами
            wait_start = time.time()
            while time.time() - wait_start < 1.0:  # 1 сек пауза между циклами
                if not running or sensor_name not in active_sensors:
                    break
                time.sleep(0.1)

        # Если повторение выключено, выходим из цикла
        if not repeat:
            break

    # Удаляем датчик из активных после завершения
    if sensor_name in active_sensors:
        del active_sensors[sensor_name]
        log_text.insert(tk.END, f"Симуляция для {sensor_name} завершена. Всего отправлено: {total_msg_count}\n")
        log_text.see(tk.END)


# Интерфейс
def create_gui():
    window = tk.Tk()
    window.title("Имитатор датчиков MQTT")
    window.geometry("500x800")  # Увеличиваем размер окна
    window.minsize(450, 600)  # Минимальный размер окна

    # Создание основного фрейма с отступами
    main_frame = tk.Frame(window, padx=10, pady=10)
    main_frame.pack(fill="both", expand=True)

    # Стили для улучшения внешнего вида
    style = ttk.Style()
    style.configure("TButton", font=("Arial", 10))
    style.configure("TLabel", font=("Arial", 10))
    style.configure("TCombobox", font=("Arial", 10))

    # Группа "Выбор источника"
    frame_source = ttk.LabelFrame(main_frame, text="Выбор источника")
    frame_source.pack(padx=5, pady=5, fill="x")

    # Создаем сетку с отступами
    for i in range(2):
        frame_source.columnconfigure(i, weight=1, pad=5)
    for i in range(2):
        frame_source.rowconfigure(i, pad=5)

    ttk.Label(frame_source, text="Выберите поле:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
    field_var = tk.StringVar()
    field_menu = ttk.Combobox(frame_source, textvariable=field_var, state="readonly", width=30)
    field_menu.grid(row=0, column=1, sticky="ew", padx=5, pady=5)

    ttk.Label(frame_source, text="Выберите датчик:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
    sensor_var = tk.StringVar()
    sensor_menu = ttk.Combobox(frame_source, textvariable=sensor_var, state="readonly", width=30)
    sensor_menu.grid(row=1, column=1, sticky="ew", padx=5, pady=5)

    # Словарь для хранения данных о полях и датчиках
    fields_data = {}
    sensor_data = {}

    # Загрузка полей
    try:
        fields = fetch_fields()
        for field in fields:
            fields_data[field["fieldName"]] = field["id"]

        field_menu["values"] = list(fields_data.keys())
        if fields_data:
            field_menu.set(list(fields_data.keys())[0])
            field_id = fields_data[field_menu.get()]

            # Загрузка датчиков для выбранного поля
            sensors = fetch_sensors_for_field(field_id)
            sensor_names = [sensor["sensorName"] for sensor in sensors]

            # Сохраняем данные о датчиках
            for sensor in sensors:
                sensor_data[sensor["sensorName"]] = {
                    "unit": sensor.get("unit", ""),
                    "accuracyClass": sensor.get("accuracyClass", ""),
                    "extraParams": sensor.get("extraParams", {})
                }

            sensor_menu["values"] = sensor_names
            if sensor_names:
                sensor_menu.set(sensor_names[0])
    except Exception as e:
        messagebox.showerror("Ошибка", f"Ошибка при загрузке данных: {e}")

    def update_sensors(*args):
        field_name = field_var.get()
        if field_name in fields_data:
            field_id = fields_data[field_name]
            try:
                sensors = fetch_sensors_for_field(field_id)
                sensor_names = [sensor["sensorName"] for sensor in sensors]

                # Обновляем данные о датчиках
                for sensor in sensors:
                    sensor_data[sensor["sensorName"]] = {
                        "unit": sensor.get("unit", ""),
                        "accuracyClass": sensor.get("accuracyClass", ""),
                        "extraParams": sensor.get("extraParams", {})
                    }

                sensor_menu["values"] = sensor_names
                if sensor_names:
                    sensor_menu.set(sensor_names[0])
                    # Автозаполнение полей на основе данных датчика
                    update_sensor_fields()
                else:
                    sensor_menu.set("")
            except Exception as e:
                messagebox.showerror("Ошибка", f"Ошибка при загрузке датчиков: {e}")

    def update_sensor_fields(*args):
        sensor_name = sensor_var.get()
        if sensor_name in sensor_data:
            sensor_info = sensor_data[sensor_name]
            # Заполняем поля данными датчика
            if sensor_info.get("unit"):
                unit_entry.delete(0, tk.END)
                unit_entry.insert(0, sensor_info["unit"])
            if sensor_info.get("accuracyClass"):
                accuracy_class_entry.delete(0, tk.END)
                accuracy_class_entry.insert(0, sensor_info["accuracyClass"])
            if sensor_info.get("extraParams"):
                extra_params_entry.delete("1.0", tk.END)
                extra_params_entry.insert("1.0", json.dumps(sensor_info["extraParams"], indent=2))

    field_var.trace("w", update_sensors)
    sensor_var.trace("w", update_sensor_fields)

    # Группа "Настройка отправки"
    frame_settings = ttk.LabelFrame(main_frame, text="Настройка отправки")
    frame_settings.pack(padx=5, pady=5, fill="x")

    # Создаем сетку с отступами
    for i in range(2):
        frame_settings.columnconfigure(i, weight=1, pad=5)
    for i in range(8):
        frame_settings.rowconfigure(i, pad=3)

    ttk.Label(frame_settings, text="Количество отправок:").grid(row=0, column=0, sticky="w", padx=5, pady=3)
    num_sends_entry = ttk.Entry(frame_settings)
    num_sends_entry.insert(0, "10")
    num_sends_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=3)

    ttk.Label(frame_settings, text="В течение (сек):").grid(row=1, column=0, sticky="w", padx=5, pady=3)
    total_time_entry = ttk.Entry(frame_settings)
    total_time_entry.insert(0, "10")
    total_time_entry.grid(row=1, column=1, sticky="ew", padx=5, pady=3)

    ttk.Label(frame_settings, text="Единицы измерения:").grid(row=2, column=0, sticky="w", padx=5, pady=3)
    unit_entry = ttk.Entry(frame_settings)
    unit_entry.insert(0, "°C")
    unit_entry.grid(row=2, column=1, sticky="ew", padx=5, pady=3)

    ttk.Label(frame_settings, text="Минимальное значение:").grid(row=3, column=0, sticky="w", padx=5, pady=3)
    min_value_entry = ttk.Entry(frame_settings)
    min_value_entry.insert(0, "15.0")
    min_value_entry.grid(row=3, column=1, sticky="ew", padx=5, pady=3)

    ttk.Label(frame_settings, text="Максимальное значение:").grid(row=4, column=0, sticky="w", padx=5, pady=3)
    max_value_entry = ttk.Entry(frame_settings)
    max_value_entry.insert(0, "35.0")
    max_value_entry.grid(row=4, column=1, sticky="ew", padx=5, pady=3)

    ttk.Label(frame_settings, text="Класс точности (опц.):").grid(row=5, column=0, sticky="w", padx=5, pady=3)
    accuracy_class_entry = ttk.Entry(frame_settings)
    accuracy_class_entry.insert(0, "±0.5%")
    accuracy_class_entry.grid(row=5, column=1, sticky="ew", padx=5, pady=3)

    ttk.Label(frame_settings, text="Доп. параметры (JSON):").grid(row=6, column=0, sticky="w", padx=5, pady=3)
    extra_params_frame = ttk.Frame(frame_settings)
    extra_params_frame.grid(row=6, column=1, sticky="ew", padx=5, pady=3)
    extra_params_entry = tk.Text(extra_params_frame, height=4, width=30)
    extra_params_entry.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    extra_params_scrollbar = ttk.Scrollbar(extra_params_frame, command=extra_params_entry.yview)
    extra_params_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    extra_params_entry.config(yscrollcommand=extra_params_scrollbar.set)
    extra_params_entry.insert(tk.END, '{"batteryLevel": "80%"}')

    repeat_var = tk.BooleanVar()
    repeat_checkbox = ttk.Checkbutton(frame_settings, text="Повторять симуляцию", variable=repeat_var)
    repeat_checkbox.grid(row=7, column=0, columnspan=2, sticky="w", padx=5, pady=3)

    # Кнопки управления
    button_frame = ttk.Frame(main_frame)
    button_frame.pack(pady=10, fill="x")

    start_button = ttk.Button(button_frame, text="Старт", style="TButton")
    start_button.pack(side="left", padx=5, expand=True, fill="x")

    stop_button = ttk.Button(button_frame, text="Стоп", style="TButton")
    stop_button.pack(side="left", padx=5, expand=True, fill="x")

    clear_log_button = ttk.Button(button_frame, text="Очистить лог", style="TButton")
    clear_log_button.pack(side="left", padx=5, expand=True, fill="x")

    # Лог событий с прокруткой
    log_frame = ttk.LabelFrame(main_frame, text="Лог событий")
    log_frame.pack(padx=5, pady=5, fill="both", expand=True)

    log_text = scrolledtext.ScrolledText(log_frame, height=15)
    log_text.pack(fill="both", expand=True, padx=5, pady=5)
    log_text.config(wrap=tk.WORD)  # Перенос по словам

    # Статус подключения
    status_frame = ttk.Frame(main_frame)
    status_frame.pack(fill="x", pady=5)

    status_label = ttk.Label(status_frame, text="Статус: ")
    status_label.pack(side="left")

    connection_status = ttk.Label(status_frame, text="Не подключено")
    connection_status.pack(side="left")

    # Функция для обновления статуса подключения
    def update_connection_status():
        if client.is_connected():
            connection_status.config(text="Подключено к MQTT брокеру", foreground="green")
        else:
            connection_status.config(text="Не подключено к MQTT брокеру", foreground="red")
        window.after(2000, update_connection_status)  # Обновление каждые 2 секунды

    # Запускаем периодическое обновление статуса
    update_connection_status()

    # Попытка подключения к MQTT брокеру при запуске
    try:
        client.connect(BROKER, PORT)
        client.loop_start()
        log_text.insert(tk.END, "Успешное подключение к MQTT брокеру\n")
    except Exception as e:
        log_text.insert(tk.END, f"Ошибка подключения к MQTT брокеру: {e}\nПопробуйте перезапустить приложение\n")

    # Логика кнопок
    def start_simulation():
        global running, threads
        sensor_name = sensor_var.get().strip()
        field_name = field_var.get().strip()
        unit = unit_entry.get().strip()
        repeat = repeat_var.get()
        accuracy_class = accuracy_class_entry.get().strip() or None  # None, если пусто
        extra_params = extra_params_entry.get("1.0", tk.END).strip() or None  # None, если пусто

        # Проверка обязательных полей
        if not sensor_name or not field_name:
            messagebox.showwarning("Предупреждение", "Выберите поле и датчик")
            return
        if not unit:
            messagebox.showwarning("Предупреждение", "Укажите единицы измерения")
            return

        # Валидация числовых значений
        try:
            num_sends = int(num_sends_entry.get())
            total_time = float(total_time_entry.get())
            min_value = float(min_value_entry.get())
            max_value = float(max_value_entry.get())
        except ValueError:
            messagebox.showerror("Ошибка", "Введите корректные числовые значения")
            return

        # Проверка валидности параметров
        if num_sends <= 0 or total_time <= 0:
            messagebox.showerror("Ошибка", "Количество отправок и время должны быть больше 0")
            return
        if min_value >= max_value:
            messagebox.showerror("Ошибка", "Минимальное значение должно быть меньше максимального")
            return

        # Проверка формата JSON для extraParams
        if extra_params:
            try:
                json.loads(extra_params)
            except json.JSONDecodeError:
                messagebox.showerror("Ошибка", "Некорректный формат JSON в дополнительных параметрах")
                return

        # Проверка на уже активный датчик
        field_id = fields_data[field_name]
        if sensor_name in active_sensors:
            messagebox.showinfo("Информация", "Датчик уже активен")
            return

        # Запуск симуляции
        active_sensors[sensor_name] = field_id
        running = True

        # Логирование запуска
        log_text.insert(tk.END,
                        f"Запуск симуляции для {sensor_name} (Поле: {field_name})\n")
        log_text.insert(tk.END,
                        f"Параметры: {min_value}-{max_value} {unit}, {num_sends} отправок за {total_time} сек.\n")
        if accuracy_class:
            log_text.insert(tk.END, f"Класс точности: {accuracy_class}\n")
        if extra_params:
            log_text.insert(tk.END, f"Доп. параметры: {extra_params}\n")
        log_text.see(tk.END)

        # Запуск в отдельном потоке
        thread = threading.Thread(
            target=simulate_sensor_data,
            args=(sensor_name, field_id, num_sends, total_time, unit, min_value, max_value, repeat, accuracy_class,
                  extra_params, log_text),
            daemon=True
        )
        thread.start()
        threads.append(thread)

    def stop_simulation():
        global running, threads
        if not running and not active_sensors:
            messagebox.showwarning("Предупреждение", "Симуляция не запущена")
            return

        running = False
        active_sensors.clear()
        log_text.insert(tk.END, "Симуляция остановлена\n")
        log_text.see(tk.END)

        # Очистка списка потоков
        threads = [t for t in threads if t.is_alive()]

    def clear_log():
        log_text.delete(1.0, tk.END)

    # Назначаем команды кнопкам
    start_button.config(command=start_simulation)
    stop_button.config(command=stop_simulation)
    clear_log_button.config(command=clear_log)

    # Обработка закрытия окна
    def on_closing():
        global running
        if active_sensors:
            if messagebox.askyesno("Подтверждение", "Есть активные датчики. Вы уверены, что хотите выйти?"):
                running = False
                active_sensors.clear()
                if client.is_connected():
                    client.disconnect()
                window.destroy()
        else:
            if client.is_connected():
                client.disconnect()
            window.destroy()

    window.protocol("WM_DELETE_WINDOW", on_closing)
    window.mainloop()


if __name__ == "__main__":
    create_gui()