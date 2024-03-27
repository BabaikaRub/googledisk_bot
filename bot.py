import os
import asyncio
import zipfile
import shutil

from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive
from aiogram import Bot, types
from aiogram.dispatcher import Dispatcher
from aiogram.utils import executor
from aiogram.types import Message
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage

# Создание машины состояний для отлова сообщений пользователя
class FSMFiles(StatesGroup):
    file_name = State()
    download_file = State()
    delete_file = State()

# Проходим аунтефикацию в гугле
gauth = GoogleAuth()

gauth.LoadCredentialsFile("mycreds.txt")


if gauth.credentials is None:
    gauth.GetFlow()
    gauth.flow.params.update({'access_type': 'offline'})
    gauth.flow.params.update({'approval_prompt': 'force'})
    gauth.LocalWebserverAuth()

elif gauth.access_token_expired:
    gauth.Refresh()
else:
    gauth.Authorize()

gauth.SaveCredentialsFile("mycreds.txt")  

drive = GoogleDrive(gauth)


# Работа с гугл диском
# Функция загрузки файла на диск 
def upload_file(file_path):
    try:
        drive = GoogleDrive(gauth)

        file_name = os.path.basename(file_path)
        gfile = drive.CreateFile({'title': file_name})
        gfile.SetContentFile(file_path)
        gfile.Upload()
        gfile.content.close()

        return gfile
    
    except Exception as _ex:
        print(_ex)


# Функция загрузки файла с диска 
def download(file_name, save_path):
    drive = GoogleDrive(gauth)
    

    file_list = drive.ListFile({'q': f"title='{file_name}'"}).GetList()
    if len(file_list) > 0:
        if file_list[0]['mimeType'] == 'application/vnd.google-apps.folder':
            download_folder(drive, file_name, save_path)
            return True, 'folder'
        else:
            gfile = drive.CreateFile({'id': file_list[0]['id']})
            gfile.GetContentFile(save_path)
            return True, 'file'

    return False


# Функция для скачивания папки с диска
def download_folder(drive, folder_name, destination_path):
    folder_list = drive.ListFile({"q": f"title='{folder_name}'"}).GetList()
    folder_id = None

    for folder in folder_list:
        if folder['title'] == folder_name and folder['mimeType'] == 'application/vnd.google-apps.folder':
            folder_id = folder['id']
            break

    if folder_id:
        folder_query = f"'{folder_id}' in parents"
        file_list = drive.ListFile({'q': folder_query}).GetList()
        
        os.mkdir(destination_path)
        for file in file_list:
            if file['mimeType'] == 'application/vnd.google-apps.folder':
                # Если это папка, создаем соответствующую папку на локальном диске
                subfolder_path = os.path.join(destination_path, file['title'])
                os.makedirs(subfolder_path, exist_ok=True)

                # Рекурсивно скачиваем содержимое внутренней папки
                download_folder(drive, file['title'], subfolder_path)
            else:
                # Если это файл, скачиваем его
                file_path = os.path.join(destination_path, file['title'])
                gfile = drive.CreateFile({'id': file['id']})
                gfile.GetContentFile(file_path)


def zip_folder(folder_path, zip_path):
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(folder_path):
            for file in files:
                file_path = os.path.join(root, file)
                zipf.write(file_path, os.path.relpath(file_path, folder_path))


# Вывод списка файлов на диске
def show_files():
    drive = GoogleDrive(gauth)

    file_list = drive.ListFile({'q': "'root' in parents and trashed=false"}).GetList()
    files = [file['title'] for file in file_list]
    return files


# Удаление файла с диска
def delete_file(file_name):
    drive = GoogleDrive(gauth)

    try:
        file_list = drive.ListFile().GetList()
        for file in file_list:
            if file['title'] == file_name:
                file.Delete()
                return True
        return False
    except:
        return False


# Бот
bot = Bot(token='YOUR_TOKEN')
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# Создаем inline клавиатуру
main_menu = types.InlineKeyboardMarkup()
list_button = types.InlineKeyboardButton("Список файлов", callback_data='file_list')
upload_button = types.InlineKeyboardButton("Выгрузить на диск", callback_data='upload')
download_button = types.InlineKeyboardButton("Загрузить с диска", callback_data='download')
delete_button = types.InlineKeyboardButton("Удалить с диска", callback_data='delete')
main_menu.add(list_button).add(upload_button).add(download_button).add(delete_button)

# Функции приветствия и меню (выполняют по сути одно и тоже, отправляют кнопки)
@dp.message_handler(commands=['start'])
async def start_command(message: Message):
    await message.reply('Привет! Я бот для работы с Google Диском', reply_markup=main_menu)


@dp.message_handler(commands=['menu'])
async def menu_command(message: Message):
    await message.reply('Меню:\n', reply_markup=main_menu)


# Хендлер запуска отлова отправленных файлов от пользователя
@dp.callback_query_handler(text='upload')
async def upload_command(callback: types.CallbackQuery, state: FSMContext):
    
    await bot.send_message(callback.from_user.id, 'Пожалуйста, отправьте файл для загрузки на Google Диск')
    await state.set_state(FSMFiles.file_name)
    await callback.answer()
        

# Хендлер обработки полученной информации (в зависимости от типа файла) и отправки ее на диск
@dp.message_handler(content_types=types.ContentType.ANY, state=FSMFiles.file_name)
async def take_file(message: types.Message, state: FSMContext):
    if message.photo:
        file_info = message.photo[-1]
        file_id = file_info.file_id
        file_name = f'photo_{file_id}.jpg'

    elif message.video:
        file_info = message.video
        file_id = file_info.file_id
        file_name = f'video_{file_id}.mp4'

    elif message.document:
        file_info = message.document
        file_id = message.document.file_id
        file_name = file_info.file_name

    else:
        await message.reply('Неизвестный тип контента. Поддерживаются только файлы, фото и видео')
        return

    new_file_path = os.path.join('documents', file_name)
    await bot.download_file_by_id(file_id, new_file_path)
    
    gfile = upload_file(new_file_path)
    
    await bot.send_message(message.from_user.id, f'Файл {file_name} успешно загружен на Google Диск')
    await bot.send_message(message.from_user.id, f'Ссылка на файл: {gfile["alternateLink"]}')

    await asyncio.sleep(1)
    os.remove(new_file_path)
    await state.finish()


# Хендлер вывода списка файлов на диске
@dp.callback_query_handler(text='file_list')
async def show_file_list(callback: types.CallbackQuery):
    files = show_files()

    if files:
        index = 1
        result_str = ''
        for file in files:
            result_str += f'{index}. {file}\n'
            index += 1
        await bot.send_message(callback.from_user.id, result_str)
    else:
        await bot.send_message(callback.from_user.id, 'На Диске нет доступных файлов')
    await callback.answer()

    return files


# Хендлер запуска отлова отправленной цифры для скачивания конкретного файла с диска
@dp.callback_query_handler(text='download', state=None)
async def download_command(callback: types.CallbackQuery, state: FSMContext):
    global files
    files = await show_file_list(callback)
    await state.set_state(FSMFiles.download_file)
    await bot.send_message(callback.from_user.id, 'Пожалуйста, отправьте мне цифру из списка файлов для загрузки с Google Диска')
    await callback.answer()
    

# Хендлер загрузки файла с диска и отправки его пользователю
@dp.message_handler(content_types=types.ContentType.TEXT, state=FSMFiles.download_file)
async def send_file(message: types.Message, state: FSMContext):
    file_num = int(message.text.strip()) - 1

    file_name = files[file_num]

    save_path = os.path.join('documents', file_name)
    if os.path.isdir(save_path):
        shutil.rmtree(save_path)

    try:
        success, type = download(file_name, save_path)

        if success and type == 'file':
            with open(save_path, 'rb') as file:
                await bot.send_document(message.from_user.id, document=file)
            os.remove(save_path)
        
        elif success and type == 'folder':
            zip_file_path = os.path.join('documents', 'Response.zip')
            zip_folder(save_path, zip_file_path)
            with open(zip_file_path, "rb") as zip_file:
                await bot.send_document(message.chat.id, zip_file)
            shutil.rmtree(save_path)
            os.remove(zip_file_path)

        else:
            await bot.send_message(message.from_user.id, f'Файл "{file_name}" не найден на Google Диске')
    except Exception as e:
        await bot.send_message(message.from_user.id, f'Произошла ошибка: {str(e)}')

    await state.finish()


@dp.callback_query_handler(text='delete', state=None)
async def delete_command(callback: types.CallbackQuery, state: FSMContext):
    global files
    files = await show_file_list(callback)
    await state.set_state(FSMFiles.delete_file)
    await bot.send_message(callback.from_user.id, 'Пожалуйста, отправьте мне цифру из списка файлов для удаления его с Google Диска')
    await callback.answer()


@dp.message_handler(content_types=types.ContentType.TEXT, state=FSMFiles.delete_file)
async def send_file(message: types.Message, state: FSMContext):
    file_num = int(message.text.strip()) - 1

    file_name = files[file_num]
    try:
        success = delete_file(file_name)

        if success:
            await bot.send_message(message.from_user.id, f'Файл {file_name} успешно удален с Диска')
        else:
            await bot.send_message(message.from_user.id, f'Файл "{file_name}" не найден на Google Диске')

    except Exception as e:
        await bot.send_message(message.from_user.id, f'Произошла ошибка: {str(e)}')

    await state.finish()


async def on_startup():
    if not os.path.isdir("documents"):
        os.mkdir("documents")

if __name__ == '__main__':
    asyncio.get_event_loop().run_until_complete((lambda: on_startup())())
    executor.start_polling(dp, skip_updates=True)
    