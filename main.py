import paho.mqtt.client as mqtt
import time
import random
import json
import tkinter as tk
from tkinter import messagebox, ttk
import requests
import threading

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

# Подключение к MQTT
client = mqtt.Client(client_id=CLIENT_ID, callback_api_version=mqtt.CallbackAPIVersion.VERSION2)


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print("Connected to MQTT broker")
    else:
        print(f"Failed to connect: {reason_code}")


client.on_connect = on_connect
try:
    client.connect(BROKER, PORT)
except Exception as e:
    print(f"Не удалось подключиться к брокеру: {e}")
    exit(1)
client.loop_start()


# Функции для работы с API
def fetch_fields():
    try:
        response = requests.get(f"{SERVER_URL}/fields", auth=(USERNAME, PASSWORD))
        if response.status_code == 200:
            return response.json()
        else:
            messagebox.showerror("Ошибка", f"Не удалось загрузить список полей: {response.status_code}")
            return []
    except Exception as e:
        messagebox.showerror("Ошибка", f"Ошибка при загрузке полей: {e}")
        return []


def fetch_sensors(field_id):
    try:
        response = requests.get(f"{SERVER_URL}/fields/{field_id}", auth=(USERNAME, PASSWORD))
        if response.status_code == 200:
            field = response.json()
            return [sensor["sensorName"] for sensor in field.get("sensors", [])]
        else:
            messagebox.showerror("Ошибка", f"Не удалось загрузить список датчиков: {response.status_code}")
            return []
    except Exception as e:
        messagebox.showerror("Ошибка", f"Ошибка при загрузке датчиков: {e}")
        return []


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

    # Рассчитываем задержку между отправками
    if num_sends > 1:
        delay_between_sends = total_time / (num_sends)
    else:
        delay_between_sends = total_time

    cycle_count = 0  # Счетчик циклов для логирования
    while running and sensor_name in active_sensors:
        cycle_count += 1
        log_text.insert(tk.END, f"Цикл {cycle_count} для {sensor_name}\n")
        log_text.see(tk.END)
        for i in range(num_sends):
            if not running or sensor_name not in active_sensors:
                break
            # Генерируем случайное значение в заданном диапазоне
            value = round(random.uniform(min_value, max_value), 1)
            # Используем текущий timestamp с миллисекундами
            current_time = time.time()
            timestamp = time.strftime("%Y-%m-%dT%H:%M:%S",
                                      time.gmtime(current_time)) + f".{int(current_time * 1000) % 1000:03d}Z"

            # Формируем данные с учётом новых полей
            payload_dict = {
                "sensorName": sensor_name,
                "value": value,
                "fieldId": field_id,
                "unit": unit,
                "timestamp": timestamp
            }
            if accuracy_class:  # Добавляем только если указано
                payload_dict["accuracyClass"] = accuracy_class
            if extra_params:  # Добавляем только если указано
                try:
                    extra_params_dict = json.loads(extra_params)
                    payload_dict["extraParams"] = extra_params_dict
                except json.JSONDecodeError:
                    log_text.insert(tk.END, f"Ошибка: Некорректный формат JSON в дополнительных параметрах\n")
                    log_text.see(tk.END)
                    return

            payload = json.dumps(payload_dict)
            result = client.publish(f"{TOPIC_PREFIX}{sensor_name}", payload)
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                log_text.insert(tk.END,
                                f"Отправка {i + 1}/{num_sends}: {value}{unit} в топик {TOPIC_PREFIX}{sensor_name} (время: {timestamp})\n")
                if accuracy_class:
                    log_text.insert(tk.END, f"Класс точности: {accuracy_class}\n")
                if extra_params:
                    log_text.insert(tk.END, f"Доп. параметры: {extra_params}\n")
                log_text.see(tk.END)
                print(f"Published to {TOPIC_PREFIX}{sensor_name}: {payload}")
            else:
                log_text.insert(tk.END, f"Ошибка отправки в топик {TOPIC_PREFIX}{sensor_name}: {result.rc}\n")
                log_text.see(tk.END)
                print(f"Failed to publish to {TOPIC_PREFIX}{sensor_name}: {result.rc}")

            # Добавляем паузу только между отправками внутри цикла
            if i < num_sends - 1:
                log_text.insert(tk.END, f"Ожидание {delay_between_sends} секунд перед следующей отправкой\n")
                log_text.see(tk.END)
                time.sleep(delay_between_sends)

        # Если повторение включено, добавляем паузу перед началом нового цикла
        if repeat and running and sensor_name in active_sensors:
            log_text.insert(tk.END, f"Ожидание {delay_between_sends} секунд перед следующим циклом\n")
            log_text.see(tk.END)
            time.sleep(delay_between_sends)

        # Если повторение выключено, выходим из цикла
        if not repeat:
            break

    # Удаляем датчик из активных после завершения
    if sensor_name in active_sensors:
        del active_sensors[sensor_name]
        log_text.insert(tk.END, f"Симуляция для {sensor_name} завершена\n")
        log_text.see(tk.END)
        # Если больше нет активных датчиков, сбрасываем флаг running
        if not active_sensors:
            running = False


# Интерфейс
def create_gui():
    window = tk.Tk()
    window.title("Имитатор датчиков")
    window.geometry("450x750")  # Увеличиваем размер окна для новых полей

    # Группа "Выбор источника"
    frame_source = tk.LabelFrame(window, text="Выбор источника", padx=10, pady=10)
    frame_source.pack(padx=10, pady=5, fill="x")

    tk.Label(frame_source, text="Выберите поле:").grid(row=0, column=0, sticky="w", pady=5)
    field_var = tk.StringVar()
    field_menu = ttk.Combobox(frame_source, textvariable=field_var, state="readonly")
    field_menu.grid(row=0, column=1, sticky="w", pady=5)

    tk.Label(frame_source, text="Выберите датчик:").grid(row=1, column=0, sticky="w", pady=5)
    sensor_var = tk.StringVar()
    sensor_menu = ttk.Combobox(frame_source, textvariable=sensor_var, state="readonly")
    sensor_menu.grid(row=1, column=1, sticky="w", pady=5)

    # Загрузка полей
    fields = fetch_fields()
    field_options = {field["fieldName"]: field["id"] for field in fields}
    field_menu["values"] = list(field_options.keys())
    if field_options:
        field_menu.set(list(field_options.keys())[0])
        field_id = field_options[field_menu.get()]
        sensors = fetch_sensors(field_id)
        sensor_menu["values"] = sensors
        if sensors:
            sensor_menu.set(sensors[0])

    def update_sensors(*args):
        field_name = field_var.get()
        if field_name in field_options:
            field_id = field_options[field_name]
            sensors = fetch_sensors(field_id)
            sensor_menu["values"] = sensors
            if sensors:
                sensor_menu.set(sensors[0])
            else:
                sensor_menu.set("")

    field_var.trace("w", update_sensors)

    # Группа "Настройка отправки"
    frame_settings = tk.LabelFrame(window, text="Настройка отправки", padx=10, pady=10)
    frame_settings.pack(padx=10, pady=5, fill="x")

    tk.Label(frame_settings, text="Количество отправок:").grid(row=0, column=0, sticky="w", pady=5)
    num_sends_entry = tk.Entry(frame_settings)
    num_sends_entry.insert(0, "10")
    num_sends_entry.grid(row=0, column=1, sticky="w", pady=5)

    tk.Label(frame_settings, text="В течение (сек):").grid(row=1, column=0, sticky="w", pady=5)
    total_time_entry = tk.Entry(frame_settings)
    total_time_entry.insert(0, "10")
    total_time_entry.grid(row=1, column=1, sticky="w", pady=5)

    tk.Label(frame_settings, text="Единицы измерения:").grid(row=2, column=0, sticky="w", pady=5)
    unit_entry = tk.Entry(frame_settings)
    unit_entry.insert(0, "°C")
    unit_entry.grid(row=2, column=1, sticky="w", pady=5)

    tk.Label(frame_settings, text="Минимальное значение:").grid(row=3, column=0, sticky="w", pady=5)
    min_value_entry = tk.Entry(frame_settings)
    min_value_entry.insert(0, "15.0")
    min_value_entry.grid(row=3, column=1, sticky="w", pady=5)

    tk.Label(frame_settings, text="Максимальное значение:").grid(row=4, column=0, sticky="w", pady=5)
    max_value_entry = tk.Entry(frame_settings)
    max_value_entry.insert(0, "35.0")
    max_value_entry.grid(row=4, column=1, sticky="w", pady=5)

    tk.Label(frame_settings, text="Класс точности (опц.):").grid(row=5, column=0, sticky="w", pady=5)
    accuracy_class_entry = tk.Entry(frame_settings)
    accuracy_class_entry.insert(0, "±0.5%")  # Пример значения, можно оставить пустым
    accuracy_class_entry.grid(row=5, column=1, sticky="w", pady=5)

    tk.Label(frame_settings, text="Доп. параметры (JSON, опц.):").grid(row=6, column=0, sticky="w", pady=5)
    extra_params_entry = tk.Text(frame_settings, height=3, width=20)
    extra_params_entry.insert(tk.END, '{"batteryLevel": "80%"}')  # Пример значения, можно оставить пустым
    extra_params_entry.grid(row=6, column=1, sticky="w", pady=5)

    repeat_var = tk.BooleanVar()
    repeat_checkbox = tk.Checkbutton(frame_settings, text="Повторять симуляцию", variable=repeat_var)
    repeat_checkbox.grid(row=7, column=0, columnspan=2, sticky="w", pady=5)

    # Кнопки
    button_frame = tk.Frame(window)
    button_frame.pack(pady=5)
    start_button = tk.Button(button_frame, text="Старт", bg="lightgreen")
    start_button.pack(side="left", padx=5)
    stop_button = tk.Button(button_frame, text="Стоп", bg="salmon")
    stop_button.pack(side="left", padx=5)
    clear_log_button = tk.Button(button_frame, text="Очистить лог", bg="lightblue")
    clear_log_button.pack(side="left", padx=5)

    # Лог событий
    log_frame = tk.LabelFrame(window, text="Лог событий", padx=10, pady=10)
    log_frame.pack(padx=10, pady=5, fill="both", expand=True)
    log_text = tk.Text(log_frame, height=10)
    log_text.pack(fill="both", expand=True)

    # Логика кнопок
    def start_simulation():
        global running
        sensor_name = sensor_var.get().strip()
        field_name = field_var.get().strip()
        unit = unit_entry.get().strip()
        repeat = repeat_var.get()
        accuracy_class = accuracy_class_entry.get().strip() or None  # Оставляем None, если пусто
        extra_params = extra_params_entry.get("1.0", tk.END).strip() or None  # Оставляем None, если пусто

        if not sensor_name or not field_name:
            messagebox.showwarning("Предупреждение", "Выберите поле и датчик")
            return
        if not unit:
            messagebox.showwarning("Предупреждение", "Укажите единицы измерения")
            return

        try:
            num_sends = int(num_sends_entry.get())
            total_time = int(total_time_entry.get())
            min_value = float(min_value_entry.get())
            max_value = float(max_value_entry.get())
        except ValueError:
            messagebox.showerror("Ошибка",
                                 "Введите числовые значения для количества отправок, времени и диапазона значений")
            return

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

        field_id = field_options[field_name]
        if sensor_name in active_sensors:
            messagebox.showinfo("Информация", "Датчик уже активен")
            return

        active_sensors[sensor_name] = field_id
        running = True
        log_text.insert(tk.END,
                        f"Запуск симуляции для {sensor_name} (Поле: {field_name}, Единицы: {unit}, Диапазон: {min_value}-{max_value}, Повторение: {'Да' if repeat else 'Нет'})\n")
        if accuracy_class:
            log_text.insert(tk.END, f"Класс точности: {accuracy_class}\n")
        if extra_params:
            log_text.insert(tk.END, f"Доп. параметры: {extra_params}\n")
        log_text.see(tk.END)

        threading.Thread(
            target=simulate_sensor_data,
            args=(sensor_name, field_id, num_sends, total_time, unit, min_value, max_value, repeat, accuracy_class,
                  extra_params, log_text),
            daemon=True
        ).start()

    def stop_simulation():
        global running
        if not running and not active_sensors:
            messagebox.showwarning("Предупреждение", "Симуляция не запущена")
            return

        running = False
        active_sensors.clear()
        log_text.insert(tk.END, "Симуляция остановлена\n")
        log_text.see(tk.END)

    def clear_log():
        log_text.delete(1.0, tk.END)

    start_button.config(command=start_simulation)
    stop_button.config(command=stop_simulation)
    clear_log_button.config(command=clear_log)

    window.mainloop()


if __name__ == "__main__":
    create_gui()