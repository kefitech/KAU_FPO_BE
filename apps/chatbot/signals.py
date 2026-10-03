"""
Auto-sync chatbot KB when POP data changes.

Fires when an admin edits a CropPackageOfPractices row via /admin/crop-pop/
(or when a script updates one) — regenerates the matching sectioned
ChatKnowledgeEntry rows so the chatbot never serves stale content.

We DO NOT write back to CropPackageOfPractices — ML side is read-only from
here.
"""

import logging

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender='database.CropPackageOfPractices')
def _sync_pop_to_chatbot_kb(sender, instance, created, **kwargs):
    from apps.chatbot.services.pop_sync import upsert_entries_for_crop, delete_entries_for_crop
    try:
        if instance.is_deleted or not instance.is_active:
            # Soft-deleted or deactivated → remove chatbot copies.
            removed = delete_entries_for_crop(instance.crop_name)
            if removed:
                logger.info(
                    f'POP sync: removed {removed} chatbot entries for '
                    f'inactive/deleted POP {instance.crop_name!r}'
                )
            return
        c, u, d = upsert_entries_for_crop(instance)
        logger.info(
            f'POP sync: {instance.crop_name!r} → chatbot KB '
            f'(created={c}, updated={u}, deleted={d})'
        )
    except Exception:
        logger.exception(f'POP sync failed for {getattr(instance, "crop_name", "?")}')


@receiver(post_delete, sender='database.CropPackageOfPractices')
def _remove_pop_from_chatbot_kb(sender, instance, **kwargs):
    from apps.chatbot.services.pop_sync import delete_entries_for_crop
    try:
        removed = delete_entries_for_crop(instance.crop_name)
        if removed:
            logger.info(
                f'POP sync: removed {removed} chatbot entries for '
                f'hard-deleted POP {instance.crop_name!r}'
            )
    except Exception:
        logger.exception(f'POP hard-delete sync failed for {getattr(instance, "crop_name", "?")}')


# ─────────────────────────────────────────────────────────────────────
# CropZoneProfile → District / Zone chatbot entries
# One edit affects both the specific zone's entry AND every district
# whose coverage includes that zone. Cheap enough to rebuild all
# zones + districts on any edit (~20 SQL queries, sub-second).
# ─────────────────────────────────────────────────────────────────────

@receiver(post_save, sender='database.CropZoneProfile')
def _sync_zone_profile_to_chatbot_kb(sender, instance, **kwargs):
    from apps.chatbot.services.zone_sync import sync_all_zones_and_districts
    try:
        result = sync_all_zones_and_districts()
        logger.info(
            f'Zone sync (post_save {instance.crop_name!r} / {instance.kau_zone!r}): '
            f'{result}'
        )
    except Exception:
        logger.exception('Zone sync failed after CropZoneProfile save')


@receiver(post_delete, sender='database.CropZoneProfile')
def _remove_zone_profile_from_chatbot_kb(sender, instance, **kwargs):
    from apps.chatbot.services.zone_sync import sync_all_zones_and_districts
    try:
        result = sync_all_zones_and_districts()
        logger.info(
            f'Zone sync (post_delete {instance.crop_name!r} / {instance.kau_zone!r}): '
            f'{result}'
        )
    except Exception:
        logger.exception('Zone sync failed after CropZoneProfile delete')


# ─────────────────────────────────────────────────────────────────────
# FPO + Product → FPO chatbot entries
# Reflects the live registry so "who sells rice in Palakkad" / "what tier
# is <FPO>" queries stay accurate.
# ─────────────────────────────────────────────────────────────────────

@receiver(post_save, sender='database.FPO')
def _sync_fpo_to_chatbot_kb(sender, instance, **kwargs):
    from apps.chatbot.services.fpo_sync import upsert_fpo_entry
    from apps.chatbot.services.product_sync import delete_product_entries_for_fpo, upsert_product_entry
    try:
        created, deleted = upsert_fpo_entry(instance)
        if created or deleted:
            logger.info(
                f'FPO sync: {instance.name!r} → chatbot KB '
                f'(created={created}, deleted={deleted})'
            )
        # If the FPO went from APPROVED → something else, drop all its
        # product entries too. If it's still APPROVED, refresh them
        # (district/tier may have changed).
        if deleted:
            pruned = delete_product_entries_for_fpo(instance.name)
            if pruned:
                logger.info(f'FPO sync: pruned {pruned} product entries for un-approved FPO {instance.name!r}')
        else:
            # A product can now have multiple stock batches — refresh every
            # batch's per-product chatbot entry.
            for product in instance.products.prefetch_related('stocks').filter(is_deleted=False):
                for stock in product.stocks.all():
                    upsert_product_entry(stock)
    except Exception:
        logger.exception(f'FPO sync failed for {getattr(instance, "name", "?")}')


@receiver(post_delete, sender='database.FPO')
def _remove_fpo_from_chatbot_kb(sender, instance, **kwargs):
    from apps.chatbot.services.fpo_sync import delete_fpo_entries
    from apps.chatbot.services.product_sync import delete_product_entries_for_fpo
    try:
        removed = delete_fpo_entries(instance.name) + delete_product_entries_for_fpo(instance.name)
        if removed:
            logger.info(
                f'FPO sync: removed {removed} chatbot entries for hard-deleted FPO {instance.name!r}'
            )
    except Exception:
        logger.exception(f'FPO delete sync failed for {getattr(instance, "name", "?")}')


@receiver(post_save, sender='database.Product')
def _sync_product_to_chatbot_kb(sender, instance, **kwargs):
    """Product changes affect the parent FPO's summary entry."""
    from apps.chatbot.services.fpo_sync import upsert_fpo_entry
    try:
        upsert_fpo_entry(instance.fpo)
    except Exception:
        logger.exception(f'Product sync failed for product {instance.id}')


@receiver(post_delete, sender='database.Product')
def _remove_product_from_chatbot_kb(sender, instance, **kwargs):
    from apps.chatbot.services.fpo_sync import upsert_fpo_entry
    try:
        upsert_fpo_entry(instance.fpo)
    except Exception:
        logger.exception(f'Product delete sync failed for product {instance.id}')


@receiver(post_save, sender='database.ProductStock')
def _sync_stock_to_chatbot_kb(sender, instance, **kwargs):
    """Stock status changes (draft → active → sold/expired) alter both
    the parent FPO's summary AND the per-product entry."""
    from apps.chatbot.services.fpo_sync import upsert_fpo_entry
    from apps.chatbot.services.product_sync import upsert_product_entry
    try:
        upsert_fpo_entry(instance.product.fpo)
        upsert_product_entry(instance)
    except Exception:
        logger.exception(f'Stock sync failed for stock {instance.id}')


@receiver(post_delete, sender='database.ProductStock')
def _remove_stock_from_chatbot_kb(sender, instance, **kwargs):
    from apps.chatbot.services.fpo_sync import upsert_fpo_entry
    from apps.chatbot.services.product_sync import delete_entry_for_stock
    try:
        # Force-delete the per-product entry — post_delete's instance still
        # has status='active' + is_deleted=False so upsert_product_entry
        # would incorrectly re-create it.
        delete_entry_for_stock(instance)
        # Also refresh the parent FPO summary so the removed listing drops out.
        upsert_fpo_entry(instance.product.fpo)
    except Exception:
        logger.exception(f'Stock delete sync failed for stock {instance.id}')
