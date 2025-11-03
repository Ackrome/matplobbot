from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from shared_lib.database import get_user_subscriptions, remove_schedule_subscription
from shared_lib.i18n import translator

router = Router()

SUBSCRIPTIONS_PER_PAGE = 5

async def get_subscriptions_keyboard(user_id: int, page: int = 0) -> InlineKeyboardBuilder:
    """Builds the keyboard for managing schedule subscriptions."""
    lang = await translator.get_user_language(user_id)
    subscriptions, total_count = await get_user_subscriptions(user_id, page=page, page_size=SUBSCRIPTIONS_PER_PAGE)
    builder = InlineKeyboardBuilder()

    for sub in subscriptions:
        builder.row(
            InlineKeyboardButton(text=f"🔔 {sub['entity_name']} ({sub['notification_time']})", callback_data="noop"),
            InlineKeyboardButton(text=translator.gettext(lang, "favorites_remove_btn"), callback_data=f"sub_del:{sub['id']}:{page}")
        )
    
    total_pages = (total_count + SUBSCRIPTIONS_PER_PAGE - 1) // SUBSCRIPTIONS_PER_PAGE
    if total_pages > 1:
        pagination_buttons = []
        if page > 0:
            pagination_buttons.append(InlineKeyboardButton(text=translator.gettext(lang, "pagination_back"), callback_data=f"sub_page:{page - 1}"))
        
        pagination_buttons.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))

        if (page + 1) < total_pages:
            pagination_buttons.append(InlineKeyboardButton(text=translator.gettext(lang, "pagination_forward"), callback_data=f"sub_page:{page + 1}"))
        
        builder.row(*pagination_buttons)

    builder.row(InlineKeyboardButton(text=translator.gettext(lang, "back_to_settings"), callback_data="back_to_settings"))
    return builder


@router.callback_query(F.data == "manage_subscriptions")
@router.callback_query(F.data.startswith("sub_page:"))
async def cq_manage_subscriptions(callback: CallbackQuery, state: FSMContext):
    """Displays the schedule subscription management interface."""
    user_id = callback.from_user.id
    lang = await translator.get_user_language(user_id)
    
    page = 0
    if callback.data.startswith("sub_page:"):
        try:
            page = int(callback.data.split(":")[1])
        except (ValueError, IndexError):
            page = 0 # Fallback to first page

    _, total_count = await get_user_subscriptions(user_id, page=page, page_size=SUBSCRIPTIONS_PER_PAGE)
    header_text = translator.gettext(lang, "subscriptions_header") if total_count > 0 else translator.gettext(lang, "subscriptions_empty")
    
    keyboard = await get_subscriptions_keyboard(user_id, page=page)
    await callback.message.edit_text(header_text, reply_markup=keyboard.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("sub_del:"))
async def cq_delete_subscription_prompt(callback: CallbackQuery):
    """Shows a confirmation prompt before deleting a schedule subscription."""
    user_id = callback.from_user.id
    lang = await translator.get_user_language(user_id)
    try:
        _, subscription_id_str, page_str = callback.data.split(":")
        subscription_id = int(subscription_id_str)

        # Find the subscription to get its name for the prompt
        subscriptions, _ = await get_user_subscriptions(user_id, page=0, page_size=1000) # Fetch all to find the name
        sub_to_delete = next((sub for sub in subscriptions if sub['id'] == subscription_id), None)

        if not sub_to_delete:
            raise ValueError("Subscription not found or already deleted.")

        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text=translator.gettext(lang, "btn_confirm_delete"), callback_data=f"sub_del_confirm:{subscription_id}:{page_str}"),
            InlineKeyboardButton(text=translator.gettext(lang, "btn_cancel_delete"), callback_data=f"sub_page:{page_str}")
        )

        await callback.message.edit_text(
            translator.gettext(lang, "subscription_confirm_delete", entity_name=sub_to_delete['entity_name']),
            reply_markup=builder.as_markup()
        )
        await callback.answer()

    except (ValueError, IndexError):
        await callback.answer(translator.gettext(lang, "subscription_info_outdated"), show_alert=True)

@router.callback_query(F.data.startswith("sub_del_confirm:"))
async def cq_confirm_delete_subscription(callback: CallbackQuery, state: FSMContext):
    """Handles the actual deletion after user confirmation."""
    user_id = callback.from_user.id
    lang = await translator.get_user_language(user_id)
    try:
        _, subscription_id_str, page_str = callback.data.split(":")
        subscription_id = int(subscription_id_str)
        deleted_entity_name = await remove_schedule_subscription(subscription_id, user_id)
        if deleted_entity_name:
            await callback.answer(translator.gettext(lang, "subscription_removed", entity_name=deleted_entity_name))
            # To refresh the list, we simulate a click on the pagination button for the original page
            callback.data = f"sub_page:{page_str}"
            await cq_manage_subscriptions(callback, state)
        else:
            await callback.answer(translator.gettext(lang, "subscription_info_outdated"), show_alert=True)
    except (ValueError, IndexError):
        await callback.answer(translator.gettext(lang, "subscription_info_outdated"), show_alert=True)