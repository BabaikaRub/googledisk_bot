import os
import asyncio

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
    num_list = State()

# Проходим аунтефикацию в гугле
gauth = GoogleAuth()
gauth.LocalWebserverAuth()


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
def download_file(file_name, save_path):
    drive = GoogleDrive(gauth)

    file_list = drive.ListFile({'q': f"title='{file_name}'"}).GetList()
    if len(file_list) > 0:
        gfile = drive.CreateFile({'id': file_list[0]['id']})
        gfile.GetContentFile(save_path)
        return True

    return False


# Вывода списка файлов на диске
def show_files():
    drive = GoogleDrive(gauth)

    file_list = drive.ListFile({'q': "'root' in parents and trashed=false"}).GetList()
    files = [file['title'] for file in file_list]
    return files


# Бот
bot = Bot(token='6949242526:AAHW1GGBn3cCNq09KJ1sbEof0x_de-FdRLk')
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# Создаем inline клавиатуру
main_menu = types.InlineKeyboardMarkup()
list_button = types.InlineKeyboardButton("Список файлов", callback_data='file_list')
upload_button = types.InlineKeyboardButton("Выгрузить на диск", callback_data='upload')
download_button = types.InlineKeyboardButton("Загрузить с диска", callback_data='download')
main_menu.add(list_button).add(upload_button).add(download_button)

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
    if callback.data == 'upload':
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
    await state.set_state(FSMFiles.num_list)
    await bot.send_message(callback.from_user.id, 'Пожалуйста, отправьте мне цифру из списка файлов для загрузки с Google Диска')
    await callback.answer()
    

# Хендлер загрузки файла с диска и отправки его пользователю
@dp.message_handler(content_types=types.ContentType.TEXT, state=FSMFiles.num_list)
async def send_file(message: types.Message, state: FSMContext):
    file_num = int(message.text.strip()) - 1
    print(file_num)

    file_name = files[file_num]

    save_path = os.path.join('documents', file_name)

    try:
        success = download_file(file_name, save_path)

        if success:
            with open(save_path, 'rb') as file:
                await bot.send_document(message.from_user.id, document=file)
            os.remove(save_path)
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
    