import discord
from discord import app_commands
from discord.ext import tasks
import a2s
import json
import os
import asyncio
import re
import time
from datetime import datetime
from typing import Optional

# ==================== КОНФИГУРАЦИЯ ====================
BOT_TOKEN = ""
CONFIG_FILE = "config.json"

# ==================== КЭШИРОВАНИЕ ====================
class QueryCache:
    """Кэширует запросы к серверам для уменьшения нагрузки"""
    
    def __init__(self, ttl=30):
        self.cache = {}
        self.ttl = ttl
    
    def get(self, ip: str, port: int) -> Optional[dict]:
        """Получает данные из кэша если они актуальны"""
        cache_key = f"{ip}:{port}"
        
        if cache_key in self.cache:
            data, timestamp = self.cache[cache_key]
            if time.time() - timestamp < self.ttl:
                return data
        return None
    
    def set(self, ip: str, port: int, data: dict):
        """Сохраняет данные в кэш"""
        cache_key = f"{ip}:{port}"
        self.cache[cache_key] = (data, time.time())
    
    def clear(self):
        """Очищает кэш"""
        self.cache.clear()

# Создаем глобальный кэш
cache = QueryCache(ttl=30)

# ==================== КЛАСС ДАННЫХ ====================
class ServerConfig:
    def __init__(self):
        self.servers = {}
        self.load_config()
    
    def load_config(self):
        """Загружает конфигурацию и добавляет недостающие поля"""
        if not os.path.exists(CONFIG_FILE):
            print("[CONFIG] Файл конфигурации не найден, будет создан новый.")
            self.servers = {}
            return

        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.servers = {int(k): v for k, v in data.items()}

                defaults = {
                    "ip": "",
                    "port": 0,
                    "display_port": None,
                    "name": "",
                    "text_channel_id": None,
                    "voice_channel_id": None,
                    "last_online": (0, 0),
                    "embed_title": "📊 {name}",
                    "embed_color": "00FF00",
                    "update_name": True,
                    "message_id": None,
                    "show_progress": True,
                    "show_map": True,
                    "show_address": True,
                    "thumbnail_url": None,
                    "footer_text": "Обновлено",
                    "design": "old",
                    "image_url": None
                }

                for server_id, server in self.servers.items():
                    for key, default_value in defaults.items():
                        if key not in server:
                            server[key] = default_value
                            print(f"[CONFIG] Добавлено поле '{key}' для сервера #{server_id}")

            print(f"[CONFIG] Загружено {len(self.servers)} серверов")

        except Exception as e:
            print(f"[CONFIG] Ошибка загрузки: {e}")
            self.servers = {}
    
    def save_config(self):
        """Сохраняет конфигурацию в файл"""
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.servers, f, indent=4, ensure_ascii=False)
            print(f"[CONFIG] Конфигурация сохранена ({len(self.servers)} серверов)")
        except Exception as e:
            print(f"[CONFIG] Ошибка сохранения: {e}")
    
    def add_server(self, ip: str, port: int, name: str, display_port: Optional[int] = None) -> Optional[int]:
        """Добавляет новый сервер и возвращает его ID"""
        for existing_id, server in self.servers.items():
            if server["ip"] == ip and server["port"] == port:
                print(f"[CONFIG] Сервер {ip}:{port} уже существует (ID: {existing_id})")
                return None
        
        new_id = max(self.servers.keys(), default=0) + 1
        
        self.servers[new_id] = {
            "ip": ip,
            "port": port,
            "display_port": display_port or port,
            "name": name,
            "text_channel_id": None,
            "voice_channel_id": None,
            "last_online": (0, 0),
            "embed_title": f"📊 {name}",
            "embed_color": "00FF00",
            "update_name": True,
            "message_id": None,
            "show_progress": True,
            "show_map": True,
            "show_address": True,
            "thumbnail_url": None,
            "footer_text": "Обновлено",
            "design": "old",
            "image_url": None
        }
        
        self.save_config()
        print(f"[CONFIG] Добавлен сервер #{new_id}: {name} ({ip}:{port})")
        return new_id

# Функции для создания embed
def create_old_embed(server_id: int, server: dict, data: dict) -> discord.Embed:
    """Создает embed в старом стиле (компактный) без карты"""
    title = server["embed_title"]
    title = title.replace("{name}", server["name"])
    title = title.replace("{online}", str(data["online"]))
    title = title.replace("{max}", str(data["max"]))

    embed = discord.Embed(
        title=title,
        color=int(server.get("embed_color", "00FF00"), 16),
        timestamp=datetime.now()
    )

    if server.get("show_progress", True):
        if data["max"] > 0:
            percentage = (data["online"] / data["max"]) * 100
            bar_length = 10
            filled = int(bar_length * (data["online"] / data["max"]))
            progress_bar = "█" * filled + "░" * (bar_length - filled)
            embed.add_field(name="👥 Онлайн", value=f"**{data['online']}**/{data['max']}", inline=True)
            embed.add_field(name="📊 Заполненность", value=f"{progress_bar} {percentage:.1f}%", inline=True)
        else:
            embed.add_field(name="👥 Онлайн", value=f"**{data['online']}**/0", inline=True)
    else:
        embed.add_field(name="👥 Онлайн", value=f"**{data['online']}**/{data['max']}", inline=False)

    # Используем display_port для отображения адреса (БЕЗ обратных кавычек)
    display_port = server.get("display_port", server["port"])
    embed.add_field(name="🌐 Адрес", value=f"{server['ip']}:{display_port}", inline=False)  # Убрал обратные кавычки

    thumbnail_url = server.get("thumbnail_url")
    if thumbnail_url:
        embed.set_thumbnail(url=thumbnail_url)

    footer_text = server.get("footer_text", "Обновлено")
    embed.set_footer(text=f"{footer_text} • 🆔: {server_id}")
    
    return embed

def create_new_embed(server_id: int, server: dict, data: dict) -> discord.Embed:
    """Создает вертикальный embed без карты"""
    
    # Выбираем цвет embed
    if data["online"] == 0:
        color = 0xFF5555  # Красный для пустого сервера
    elif data["online"] < data["max"] * 0.5:
        color = 0xFFAA00  # Оранжевый для малого онлайна
    else:
        color = int(server.get("embed_color", "00FF00"), 16)  # Из конфига
    
    embed = discord.Embed(
        title=f"🎮 {server['name']}",
        color=color,
        timestamp=datetime.now()
    )
    
    # IP-адрес с отображаемым портом (БЕЗ обратных кавычек для удаления черного фона)
    display_port = server.get("display_port", server["port"])
    embed.add_field(
        name="🌐 IP-адрес", 
        value=f"{server['ip']}:{display_port}",  # Убрал обратные кавычки ``
        inline=False
    )

    # Онлайн с прогресс-баром (если включено)
    online_value = f"**{data['online']} / {data['max']}**"
    
    if server.get("show_progress", True) and data["max"] > 0:
        percentage = (data["online"] / data["max"]) * 100
        bar_length = 15
        filled = int(bar_length * (data["online"] / data["max"]))
        progress_bar = "█" * filled + "░" * (bar_length - filled)
        online_value += f"\n`{progress_bar}` {percentage:.1f}%"
    
    embed.add_field(name="👥 Онлайн", value=online_value, inline=False)
    
    # Большое изображение на всю ширину
    image_url = server.get("image_url") or server.get("thumbnail_url")
    if image_url:
        embed.set_image(url=image_url)
    
    # Футер с текстом "Обновлено" и временем
    embed.set_footer(text="Обновлено")
    
    return embed

# ==================== ИНИЦИАЛИЗАЦИЯ ====================
intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)
config = ServerConfig()

# ==================== ОСНОВНЫЕ ФУНКЦИИ ====================
async def get_server_info(ip: str, port: int) -> Optional[dict]:
    """Получает информацию о сервере с использованием кэша"""
    cached_data = cache.get(ip, port)
    if cached_data:
        print(f"[CACHE] Использую кэш для {ip}:{port}")
        return cached_data
    
    try:
        info = await client.loop.run_in_executor(
            None, a2s.info, (ip, port), 5.0
        )
        data = {
            "online": info.player_count,
            "max": info.max_players,
            "name": info.server_name,
            "map": info.map_name
        }
        
        cache.set(ip, port, data)
        print(f"[CACHE] Сохранил в кэш {ip}:{port} - {data['online']}/{data['max']}")
        return data
        
    except Exception as e:
        print(f"[A2S] Ошибка запроса к {ip}:{port}: {e}")
        return None

async def find_bot_message(channel: discord.TextChannel) -> Optional[discord.Message]:
    """Ищет последнее сообщение от бота с embed в канале"""
    try:
        async for message in channel.history(limit=15):
            if message.author == client.user and len(message.embeds) > 0:
                return message
    except Exception as e:
        print(f"[FIND] Ошибка поиска сообщений: {e}")
    return None

async def update_text_embed(server_id: int, data: dict):
    """Обновляет embed плашку только при изменении данных"""
    server = config.servers[server_id]
    channel_id = server.get("text_channel_id")
    if not channel_id:
        return None

    channel = client.get_channel(channel_id)
    if not isinstance(channel, discord.TextChannel):
        return None

    # Выбираем дизайн
    design = server.get("design", "old")
    if design == "new":
        embed = create_new_embed(server_id, server, data)
    else:
        embed = create_old_embed(server_id, server, data)

    message_id = server.get("message_id")
    message = None

    if message_id:
        try:
            message = await channel.fetch_message(message_id)
            # ✅ ВАЖНО: Проверяем, изменился ли контент, сравнивая с текущим embed
            if (message and len(message.embeds) > 0 and 
                message.embeds[0].description == embed.description and
                message.embeds[0].title == embed.title and
                message.embeds[0].color == embed.color):
                # Контент не изменился, пропускаем обновление
                print(f"[UPDATE] Данные для сервера #{server_id} не изменились, пропускаю обновление плашки")
                return message
        except discord.NotFound:
            print(f"[UPDATE] Сообщение #{message_id} не найдено")
            server["message_id"] = None
            message = None
        except Exception as e:
            print(f"[UPDATE] Ошибка поиска сообщения #{message_id}: {e}")

    if not message:
        message = await find_bot_message(channel)
        if message:
            server["message_id"] = message.id
            print(f"[UPDATE] Найдено существующее сообщение #{message.id}")

    try:
        if message:
            await message.edit(embed=embed)
        else:
            message = await channel.send(embed=embed)
            server["message_id"] = message.id
            print(f"[UPDATE] Отправлено новое сообщение #{message.id}")

        config.save_config()
        return message

    except discord.HTTPException as e:
        # ✅ ВАЖНО: Обрабатываем ошибку rate limit (429) для текстовых сообщений
        if e.status == 429:
            retry_after = e.response.headers.get('Retry-After', 5)
            print(f"[UPDATE] Discord rate limit при обновлении плашки! Жду {retry_after} секунд...")
            await asyncio.sleep(float(retry_after))
            # Пробуем снова после ожидания
            try:
                if message:
                    await message.edit(embed=embed)
                else:
                    message = await channel.send(embed=embed)
                    server["message_id"] = message.id
                print(f"[UPDATE] Повторное обновление плашки после ожидания")
                config.save_config()
                return message
            except Exception as e2:
                print(f"[UPDATE] Ошибка повторного обновления плашки: {e2}")
        else:
            print(f"[ERROR] Не удалось обновить плашку #{server_id}: {e}")
        return None
    except Exception as e:
        print(f"[ERROR] Не удалось обновить плашку #{server_id}: {e}")
        return None

async def update_voice_channel_name(server_id: int, data: dict):
    """Обновляет название голосового канала только при изменении данных"""
    server = config.servers[server_id]
    
    # Проверяем включена ли опция
    if not server.get("update_name", True):
        return

    channel_id = server.get("voice_channel_id")
    if not channel_id:
        return

    channel = client.get_channel(channel_id)
    if not isinstance(channel, discord.VoiceChannel):
        print(f"[VOICE] Канал #{channel_id} не является голосовым для сервера #{server_id}")
        return

    # Выбираем эмодзи в зависимости от онлайна
    if data["online"] > 0:
        emoji = "🟢"
    else:
        emoji = "🔴"
    
    # Формируем новое имя (макс 32 символа в Discord)
    server_name = server['name'][:15] if len(server['name']) > 15 else server['name']
    new_name = f"{emoji} {data['online']}/{data['max']} | {server_name}"
    new_name = new_name[:32]
    
    # ✅ ВАЖНО: Проверяем, изменилось ли имя, чтобы не отправлять лишний запрос в Discord
    if channel.name == new_name:
        return  # Имя не изменилось, выходим
    
    try:
        await channel.edit(name=new_name)
        print(f"[VOICE] Обновлено имя канала для сервера #{server_id}: {new_name}")
    except discord.Forbidden:
        print(f"[VOICE] Нет прав для изменения канала #{channel_id}")
    except discord.HTTPException as e:
        # ✅ ВАЖНО: Обрабатываем ошибку rate limit (429)
        if e.status == 429:
            retry_after = e.response.headers.get('Retry-After', 5)
            print(f"[VOICE] Discord rate limit! Жду {retry_after} секунд...")
            await asyncio.sleep(float(retry_after))
            # Пробуем снова после ожидания
            try:
                await channel.edit(name=new_name)
                print(f"[VOICE] Повторное обновление имени канала после ожидания")
            except Exception as e2:
                print(f"[VOICE] Ошибка повторного обновления: {e2}")
        else:
            print(f"[VOICE] Ошибка обновления канала #{server_id}: {e}")
async def update_server_status(server_id: int):
    """Обновляет статус конкретного сервера"""
    if server_id not in config.servers:
        return

    server = config.servers[server_id]
    data = await get_server_info(server["ip"], server["port"])

    if not data:
        return

    server["last_online"] = (data["online"], data["max"])

    if server.get("text_channel_id"):
        await update_text_embed(server_id, data)

    if server.get("voice_channel_id"):
        await update_voice_channel_name(server_id, data)

    config.save_config()

# ==================== ФОНОВЫЕ ЗАДАЧИ ====================
@tasks.loop(seconds=60)
async def auto_update_servers():
    """Автоматическое обновление всех серверов с защитой от rate limit"""
    if not config.servers:
        return
    
    print(f"[TASK] Начинаю обновление {len(config.servers)} серверов...")
    start_time = time.time()
    
    successful = 0
    failed = 0
    
    for server_id in config.servers.keys():
        try:
            await update_server_status(server_id)
            successful += 1
        except Exception as e:
            print(f"[TASK] Ошибка обновления сервера #{server_id}: {e}")
            failed += 1
        
        # ✅ ВАЖНО: Задержка 2 секунды между серверами для избежания лимита Discord
        await asyncio.sleep(2)
    
    elapsed = time.time() - start_time
    print(f"[TASK] Обновление завершено: {successful} успешно, {failed} с ошибками. Время: {elapsed:.2f}с")

# ==================== SLASH-КОМАНДЫ ====================
@tree.command(name="voice_test", description="Тест обновления голосового канала")
@app_commands.describe(server_id="ID сервера")
async def voice_test(interaction: discord.Interaction, server_id: int):
    """Тестирует обновление голосового канала"""
    if server_id not in config.servers:
        await interaction.response.send_message("❌ Сервер не найден", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    
    server = config.servers[server_id]
    
    if not server.get("voice_channel_id"):
        await interaction.followup.send("❌ Голосовой канал не настроен", ephemeral=True)
        return
    
    data = await get_server_info(server["ip"], server["port"])
    
    if not data:
        await interaction.followup.send("❌ Не удалось получить данные сервера", ephemeral=True)
        return
    
    try:
        await update_voice_channel_name(server_id, data)
        
        channel = client.get_channel(server["voice_channel_id"])
        if channel:
            await interaction.followup.send(
                f"✅ Голосовой канал обновлен\n"
                f"**Текущее имя:** {channel.name}\n"
                f"**Онлайн:** {data['online']}/{data['max']}",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"⚠️ Канал не найден, но функция обновления выполнена",
                ephemeral=True
            )
            
    except Exception as e:
        await interaction.followup.send(f"❌ Ошибка: {e}", ephemeral=True)

@tree.command(name="design_preview", description="Предпросмотр разных дизайнов плашки")
@app_commands.describe(
    server_id="ID сервера",
    design="Тип дизайна для предпросмотра"
)
@app_commands.choices(design=[
    app_commands.Choice(name="📊 Старый дизайн", value="old"),
    app_commands.Choice(name="🎨 Новый дизайн", value="new")
])
async def design_preview(
    interaction: discord.Interaction,
    server_id: int,
    design: str
):
    """Показывает предпросмотр выбранного дизайна"""
    if server_id not in config.servers:
        await interaction.response.send_message("❌ Сервер не найден", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    
    server = config.servers[server_id]
    data = await get_server_info(server["ip"], server["port"])
    
    if not data:
        await interaction.followup.send("❌ Не удалось получить данные сервера", ephemeral=True)
        return
    
    if design == "new":
        embed = create_new_embed(server_id, server, data)
        embed.set_footer(text=f"{embed.footer.text} • Предпросмотр нового дизайна")
    else:
        embed = create_old_embed(server_id, server, data)
        embed.set_footer(text=f"{embed.footer.text} • Предпросмотр старого дизайна")
    
    design_names = {"old": "📊 Старый дизайн", "new": "🎨 Новый дизайн"}
    
    await interaction.followup.send(
        content=f"👁️ **Предпросмотр: {design_names[design]}**",
        embed=embed,
        ephemeral=True
    )

@tree.command(name="design_set", description="Сменить дизайн плашки")
@app_commands.describe(
    server_id="ID сервера",
    design="Тип дизайна",
    image_url="URL изображения для нового дизайна (опционально)"
)
@app_commands.choices(design=[
    app_commands.Choice(name="📊 Старый дизайн (компактный)", value="old"),
    app_commands.Choice(name="🎨 Новый дизайн (с изображением)", value="new")
])
async def design_set(
    interaction: discord.Interaction,
    server_id: int,
    design: str,
    image_url: Optional[str] = None
):
    """Устанавливает дизайн плашки сервера"""
    if server_id not in config.servers:
        await interaction.response.send_message("❌ Сервер не найден", ephemeral=True)
        return
    
    server = config.servers[server_id]
    server["design"] = design
    
    if image_url:
        if image_url.startswith(('http://', 'https://')):
            server["image_url"] = image_url
        else:
            await interaction.response.send_message(
                "❌ URL должен начинаться с http:// или https://",
                ephemeral=True
            )
            return
    
    config.save_config()
    
    data = await get_server_info(server["ip"], server["port"])
    if data:
        await update_text_embed(server_id, data)
    
    design_names = {"old": "📊 Старый дизайн", "new": "🎨 Новый дизайн"}
    
    embed = discord.Embed(
        title="✅ Дизайн обновлен",
        color=discord.Color.green()
    )
    embed.add_field(name="Сервер", value=server["name"], inline=True)
    embed.add_field(name="ID", value=str(server_id), inline=True)
    embed.add_field(name="Дизайн", value=design_names[design], inline=True)
    
    if design == "new" and server.get("image_url"):
        embed.add_field(name="Изображение", value="✅ Установлено", inline=False)
        if image_url:
            embed.set_image(url=image_url)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="server_add", description="Добавить новый сервер для мониторинга")
@app_commands.describe(
    ip="IP адрес сервера",
    port="Порт для A2S запросов",
    display_port="Порт для отображения (если отличается)",
    name="Название сервера"
)
async def server_add(interaction: discord.Interaction, ip: str, port: int, name: str, display_port: Optional[int] = None):
    """Добавляет новый сервер"""
    await interaction.response.defer(ephemeral=True)  # Убрали thinking=True

    # Проверка на дубликат
    for sid, server in config.servers.items():
        if server["ip"] == ip and server["port"] == port:
            await interaction.followup.send(
                f"⚠️ Сервер `{ip}:{port}` уже добавлен (ID: {sid}).",
                ephemeral=True
            )
            return

    data = await get_server_info(ip, port)
    if not data:
        await interaction.followup.send(
            f"❌ Не удалось подключиться к `{ip}:{port}`. Проверьте IP и порт.",
            ephemeral=True
        )
        return
    
    server_id = config.add_server(ip, port, name, display_port)
    
    if server_id is None:
        await interaction.followup.send(
            "❌ Не удалось добавить сервер. Возможно, он уже существует.",
            ephemeral=True
        )
        return

    embed = discord.Embed(
        title="✅ Сервер добавлен",
        description=f"Сервер **{name}** добавлен в мониторинг.",
        color=discord.Color.green()
    )
    embed.add_field(name="ID", value=str(server_id), inline=True)
    embed.add_field(name="Запросный порт", value=str(port), inline=True)
    
    if display_port and display_port != port:
        embed.add_field(name="Отображаемый порт", value=str(display_port), inline=True)
    
    embed.add_field(name="Адрес для отображения", 
                   value=f"`{ip}:{display_port or port}`", 
                   inline=False)
    embed.add_field(name="Текущий онлайн", value=f"{data['online']}/{data['max']}", inline=False)

    await interaction.followup.send(embed=embed, ephemeral=True)

@tree.command(name="clear_cache", description="Очистить кэш запросов")
async def clear_cache(interaction: discord.Interaction):
    """Очищает кэш запросов к серверам"""
    cache.clear()
    await interaction.response.send_message(
        "✅ Кэш запросов очищен. Следующие запросы будут свежими.",
        ephemeral=True
    )

@tree.command(name="server_list", description="Показать список всех серверов")
async def server_list(interaction: discord.Interaction):
    """Показывает список серверов"""
    await interaction.response.defer(ephemeral=True, thinking=True)

    if not config.servers:
        await interaction.followup.send(
            "📭 Список серверов пуст. Добавьте сервер командой `/server_add`.",
            ephemeral=True
        )
        return

    embed = discord.Embed(
        title="📋 Список серверов",
        description=f"Всего серверов: {len(config.servers)}",
        color=discord.Color.blue()
    )

    for server_id, server in config.servers.items():
        status = "✅ Настроен" if server["text_channel_id"] else "⚠️ Требует настройки"
        text_ch = f"<#{server['text_channel_id']}>" if server["text_channel_id"] else "—"
        voice_ch = f"<#{server['voice_channel_id']}>" if server["voice_channel_id"] else "—"
        
        display_port = server.get("display_port", server["port"])
        port_info = f"{server['port']} → {display_port}" if server.get("display_port") else f"{server['port']}"

        embed.add_field(
            name=f"🆔 #{server_id} — {server['name']}",
            value=f"**IP:** {server['ip']}\n"
                  f"**Порты:** {port_info}\n"
                  f"**Текст. канал:** {text_ch}\n"
                  f"**Голос. канал:** {voice_ch}\n"
                  f"**Статус:** {status}\n"
                  f"**Онлайн:** {server['last_online'][0]}/{server['last_online'][1]}",
            inline=False
        )

    await interaction.followup.send(embed=embed, ephemeral=True)

@tree.command(name="set_display_port", description="Изменить отображаемый порт")
@app_commands.describe(
    server_id="ID сервера",
    display_port="Новый порт для отображения"
)
async def set_display_port(interaction: discord.Interaction, server_id: int, display_port: int):
    """Изменяет порт для отображения в плашке"""
    if server_id not in config.servers:
        await interaction.response.send_message("❌ Сервер не найден", ephemeral=True)
        return
    
    if not (1 <= display_port <= 65535):
        await interaction.response.send_message("❌ Порт должен быть в диапазоне 1-65535", ephemeral=True)
        return
    
    server = config.servers[server_id]
    old_port = server.get("display_port", server["port"])
    server["display_port"] = display_port
    
    config.save_config()
    
    # Обновляем плашку
    data = await get_server_info(server["ip"], server["port"])
    if data:
        await update_text_embed(server_id, data)
    
    await interaction.response.send_message(
        f"✅ Отображаемый порт для **{server['name']}** изменён:\n"
        f"**Было:** `{server['ip']}:{old_port}`\n"
        f"**Стало:** `{server['ip']}:{display_port}`",
        ephemeral=True
    )

@tree.command(name="server_set_channel", description="Настроить каналы для отображения")
@app_commands.describe(
    server_id="ID сервера",
    channel_type="Тип канала",
    channel="Выберите канал"
)
@app_commands.choices(channel_type=[
    app_commands.Choice(name="Текстовый канал (для плашки)", value="text"),
    app_commands.Choice(name="Голосовой канал (для онлайн-статуса)", value="voice")
])
async def server_set_channel(
    interaction: discord.Interaction,
    server_id: int,
    channel_type: str,
    channel: discord.abc.GuildChannel
):
    """Настраивает каналы для сервера"""
    if server_id not in config.servers:
        await interaction.response.send_message(
            f"❌ Сервер с ID `{server_id}` не найден.",
            ephemeral=True
        )
        return

    if channel_type == "text" and not isinstance(channel, discord.TextChannel):
        await interaction.response.send_message(
            "❌ Выберите именно текстовый канал.",
            ephemeral=True
        )
        return
    elif channel_type == "voice" and not isinstance(channel, discord.VoiceChannel):
        await interaction.response.send_message(
            "❌ Выберите именно голосовой канал.",
            ephemeral=True
        )
        return

    server = config.servers[server_id]

    if channel_type == "text":
        server["text_channel_id"] = channel.id
    else:
        server["voice_channel_id"] = channel.id

    config.save_config()

    await interaction.response.send_message(
        f"✅ {'Текстовый' if channel_type == 'text' else 'Голосовой'} канал "
        f"{channel.mention} установлен для сервера #{server_id}.",
        ephemeral=True
    )

    try:
        await update_server_status(server_id)
    except Exception as e:
        print(f"[SET_CHANNEL] Ошибка обновления после настройки канала: {e}")

@tree.command(name="server_test", description="Протестировать подключение к серверу")
@app_commands.describe(server_id="ID сервера")
async def server_test(interaction: discord.Interaction, server_id: int):
    """Тестирует подключение к серверу"""
    if server_id not in config.servers:
        await interaction.response.send_message(
            f"❌ Сервер с ID `{server_id}` не найден.",
            ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True, thinking=True)

    server = config.servers[server_id]
    data = await get_server_info(server["ip"], server["port"])

    if not data:
        await interaction.followup.send(
            f"❌ Сервер **{server['name']}** не отвечает.",
            ephemeral=True
        )
        return

    embed = discord.Embed(
        title=f"📊 Тест сервера #{server_id}",
        color=discord.Color.green(),
        timestamp=datetime.now()
    )
    
    display_port = server.get("display_port", server["port"])
    embed.add_field(name="Название", value=data["name"], inline=True)
    embed.add_field(name="Онлайн", value=f"{data['online']}/{data['max']}", inline=True)
    embed.add_field(name="Запросный порт", value=f"`{server['port']}`", inline=False)
    embed.add_field(name="Отображаемый порт", value=f"`{display_port}`", inline=True)
    embed.add_field(name="Адрес для плашки", value=f"`{server['ip']}:{display_port}`", inline=False)

    await interaction.followup.send(embed=embed, ephemeral=True)

@tree.command(name="server_remove", description="Удалить сервер из мониторинга")
@app_commands.describe(server_id="ID сервера")
async def server_remove(interaction: discord.Interaction, server_id: int):
    """Удаляет сервер"""
    if server_id not in config.servers:
        await interaction.response.send_message(
            f"❌ Сервер с ID `{server_id}` не найден.",
            ephemeral=True
        )
        return

    server_name = config.servers[server_id]["name"]
    
    if config.servers[server_id].get("text_channel_id") and config.servers[server_id].get("message_id"):
        try:
            channel = client.get_channel(config.servers[server_id]["text_channel_id"])
            if channel:
                message = await channel.fetch_message(config.servers[server_id]["message_id"])
                await message.delete()
        except:
            pass

    del config.servers[server_id]
    config.save_config()

    await interaction.response.send_message(
        f"✅ Сервер **{server_name}** (ID: {server_id}) удалён.",
        ephemeral=True
    )

@tree.command(name="server_customize", description="Настроить внешний вид плашки")
@app_commands.describe(
    server_id="ID сервера",
    title="Заголовок (используйте {name}, {online}, {max})",
    color="Цвет в HEX (например, FF0000)",
    show_progress="Показывать прогресс-бар?",
    show_address="Показывать адрес?",
    display_port="Порт для отображения (если отличается)",
    thumbnail_url="URL картинки для thumbnail",
    footer_text="Текст в подвале"
)
async def server_customize(
    interaction: discord.Interaction,
    server_id: int,
    title: str = None,
    color: str = None,
    show_progress: bool = None,
    show_address: bool = None,
    display_port: Optional[int] = None,
    thumbnail_url: str = None,
    footer_text: str = None
):
    """Кастомизирует внешний вид плашки (без карты)"""
    if server_id not in config.servers:
        await interaction.response.send_message(
            f"❌ Сервер с ID `{server_id}` не найден.",
            ephemeral=True
        )
        return

    server = config.servers[server_id]
    changes = []

    if title is not None:
        server["embed_title"] = title
        changes.append(f"**Заголовок:** `{title}`")

    if color is not None:
        if re.match(r'^[0-9A-Fa-f]{6}$', color):
            server["embed_color"] = color.upper()
            changes.append(f"**Цвет:** `#{color.upper()}`")
        else:
            await interaction.response.send_message(
                "❌ Неверный формат цвета. Используйте HEX (например, FF0000).",
                ephemeral=True
            )
            return

    if show_progress is not None:
        server["show_progress"] = show_progress
        changes.append(f"**Прогресс-бар:** {'включен' if show_progress else 'выключен'}")

    if show_address is not None:
        server["show_address"] = show_address
        changes.append(f"**Адрес:** {'показан' if show_address else 'скрыт'}")

    if display_port is not None:
        server["display_port"] = display_port
        changes.append(f"**Отображаемый порт:** `{display_port}`")

    if thumbnail_url is not None:
        if thumbnail_url.startswith(('http://', 'https://')):
            server["thumbnail_url"] = thumbnail_url
            changes.append("**Thumbnail:** установлен")
        else:
            await interaction.response.send_message(
                "❌ URL должен начинаться с http:// или https://",
                ephemeral=True
            )
            return

    if footer_text is not None:
        server["footer_text"] = footer_text
        changes.append(f"**Подвал:** `{footer_text}`")

    config.save_config()
    
    # Обновляем плашку
    data = await get_server_info(server["ip"], server["port"])
    if data:
        await update_text_embed(server_id, data)

    embed = discord.Embed(
        title="✅ Настройки плашки обновлены",
        description=f"Изменения для сервера **{server['name']}** (ID: {server_id}):",
        color=discord.Color.green()
    )

    if changes:
        embed.add_field(name="Применённые изменения", value="\n".join(changes), inline=False)
    else:
        embed.add_field(name="ℹ️", value="Никаких изменений не было применено.", inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="server_preview", description="Предпросмотр текущего вида плашки")
@app_commands.describe(server_id="ID сервера")
async def server_preview(interaction: discord.Interaction, server_id: int):
    """Показывает, как выглядит плашка сервера"""
    if server_id not in config.servers:
        await interaction.response.send_message(
            f"❌ Сервер с ID `{server_id}` не найден.",
            ephemeral=True
        )
        return

    server = config.servers[server_id]
    data = await get_server_info(server["ip"], server["port"])

    if not data:
        await interaction.response.send_message(
            f"❌ Не удалось получить данные с сервера.",
            ephemeral=True
        )
        return

    title = server["embed_title"]
    title = title.replace("{name}", server["name"])
    title = title.replace("{online}", str(data["online"]))
    title = title.replace("{max}", str(data["max"]))

    embed = discord.Embed(
        title=title,
        color=int(server.get("embed_color", "00FF00"), 16),
        timestamp=datetime.now()
    )

    if server.get("show_progress", True):
        if data["max"] > 0:
            percentage = (data["online"] / data["max"]) * 100
            bar_length = 10
            filled = int(bar_length * (data["online"] / data["max"]))
            progress_bar = "█" * filled + "░" * (bar_length - filled)
            embed.add_field(name="👥 Онлайн", value=f"**{data['online']}**/{data['max']}", inline=True)
            embed.add_field(name="📊 Заполненность", value=f"{progress_bar} {percentage:.1f}%", inline=True)
        else:
            embed.add_field(name="👥 Онлайн", value=f"**{data['online']}**/0", inline=True)
    else:
        embed.add_field(name="👥 Онлайн", value=f"**{data['online']}**/{data['max']}", inline=False)

    if server.get("show_map", True):
        embed.add_field(name="🗺️ Карта", value=data["map"], inline=False)

    if server.get("show_address", True):
        embed.add_field(name="🌐 Адрес", value=f"`{server['ip']}:{server['port']}`", inline=False)

    if server.get("thumbnail_url"):
        embed.set_thumbnail(url=server["thumbnail_url"])

    footer_text = server.get("footer_text", "Обновлено")
    embed.set_footer(text=f"{footer_text} • 🆔: {server_id} • Предпросмотр")

    await interaction.response.send_message(
        content="👁️ **Предпросмотр плашки** (так она выглядит в канале):",
        embed=embed,
        ephemeral=True
    )

@tree.command(name="bot_help", description="Показать справку по командам")
async def bot_help(interaction: discord.Interaction):
    """Показывает справку (без упоминания карты)"""
    embed = discord.Embed(
        title="📖 Справка по командам бота",
        description="Бот для мониторинга серверов",
        color=discord.Color.blue()
    )

    commands = [
        ("`/server_add <ip> <port> <name>`", "Добавить новый сервер"),
        ("`/server_list`", "Показать все серверы"),
        ("`/server_set_channel <id> <тип> <канал>`", "Настроить каналы"),
        ("`/server_test <id>`", "Протестировать подключение"),
        ("`/server_customize <id> [опции...]`", "Настроить вид плашки"),
        ("`/design_set <id> <дизайн> [изображение]`", "Сменить дизайн плашки"),
        ("`/design_preview <id> <дизайн>`", "Предпросмотр дизайна"),
        ("`/voice_test <id>`", "Тест голосового канала"),
        ("`/clear_cache`", "Очистить кэш запросов"),
        ("`/set_image <id> [url] [reset]`", "Установить изображение"),
        ("`/server_remove <id>`", "Удалить сервер"),
        ("`/bot_help`", "Эта справка")
    ]

    for cmd, desc in commands:
        embed.add_field(name=cmd, value=desc, inline=False)
    
    embed.add_field(
        name="🎨 Дизайны плашек", 
        value="• **Старый**: Компактный\n• **Новый**: Вертикальный с изображением", 
        inline=False
    )

    embed.set_footer(text=f"📊 Мониторится серверов: {len(config.servers)}")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="panel_recreate", description="Удалить старую плашку и создать новую")
@app_commands.describe(server_id="ID сервера")
async def panel_recreate(interaction: discord.Interaction, server_id: int):
    """Пересоздает плашку сервера (удаляет старую, создает новую)"""
    if server_id not in config.servers:
        await interaction.response.send_message("❌ Сервер не найден", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    
    server = config.servers[server_id]
    
    if not server.get("text_channel_id"):
        await interaction.followup.send(
            "❌ У этого сервера не настроен текстовый канал. Используйте `/server_set_channel`",
            ephemeral=True
        )
        return
    
    data = await get_server_info(server["ip"], server["port"])
    
    if not data:
        await interaction.followup.send("❌ Не удалось получить данные сервера", ephemeral=True)
        return
    
    channel = client.get_channel(server["text_channel_id"])
    if not isinstance(channel, discord.TextChannel):
        await interaction.followup.send("❌ Канал не найден или не текстовый", ephemeral=True)
        return
    
    if server.get("message_id"):
        try:
            old_message = await channel.fetch_message(server["message_id"])
            await old_message.delete()
            print(f"[RECREATE] Удалена старая плашка #{server['message_id']}")
        except discord.NotFound:
            print(f"[RECREATE] Старая плашка уже удалена")
        except Exception as e:
            print(f"[RECREATE] Ошибка удаления старой плашки: {e}")
    
    design = server.get("design", "old")
    if design == "new":
        embed = create_new_embed(server_id, server, data)
    else:
        embed = create_old_embed(server_id, server, data)
    
    try:
        new_message = await channel.send(embed=embed)
        server["message_id"] = new_message.id
        config.save_config()
        
        await interaction.followup.send(
            f"✅ Плашка сервера **{server['name']}** пересоздана\n"
            f"**Канал:** {channel.mention}\n"
            f"**Ссылка:** {new_message.jump_url}",
            ephemeral=True
        )
    except Exception as e:
        await interaction.followup.send(f"❌ Ошибка при создании плашки: {e}", ephemeral=True)

# ==================== ЗАПУСК БОТА ====================
@client.event
async def on_ready():
    print(f"✅ Бот {client.user} запущен!")
    print(f"📊 Загружено серверов: {len(config.servers)}")
    print(f"🌐 Бот находится на {len(client.guilds)} серверах")

    try:
        synced = await tree.sync()
        print(f"🔗 Глобально синхронизировано {len(synced)} команд")
    except Exception as e:
        print(f"⚠️ Ошибка синхронизации команд: {e}")
        for guild in client.guilds:
            try:
                await tree.sync(guild=guild)
                print(f"🔗 Синхронизировано для сервера: {guild.name}")
            except Exception as e2:
                print(f"⚠️ Ошибка для сервера {guild.name}: {e2}")

    auto_update_servers.start()
    print("🔄 Автообновление запущено")

def main():
    if BOT_TOKEN == "ВАШ_ТОКЕН":
        print("❌ ОШИБКА: Замените BOT_TOKEN на ваш токен из Discord Developer Portal!")
        return

    client.run(BOT_TOKEN)

if __name__ == "__main__":
    main()