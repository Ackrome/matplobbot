const CALENDAR_PLATFORM_KEY = "mpb_calendar_sync_platform";
const CALENDAR_REVEALED_PROFILES_KEY = "mpb_calendar_sync_revealed_profiles";

let calendarPlatform = loadCalendarPlatform();
let revealedCalendarProfileIds = loadRevealedCalendarProfileIds();
window.calendarCurrentViewMode = 'all';

function createDefaultCalendarSubscriptionState() {
    return {
        loading: false,
        hasError: false,
        justReset: false,
        enabled: false,
        sync_enabled: true,
        selected_profile_id: 'all',
        profile_limit: 0,
        eligibility: {
            available: false,
            has_telegram_link: false,
            has_active_subscriptions: false,
            reasons: [],
            detail: ''
        },
        source_summary: {
            total_subscriptions: 0,
            active_subscriptions: 0,
            active_entities: 0
        },
        profiles: []
    };
}

calendarSubscriptionState = createDefaultCalendarSubscriptionState();

function loadCalendarPlatform() {
    try {
        const saved = localStorage.getItem(CALENDAR_PLATFORM_KEY);
        if (saved === 'apple' || saved === 'google' || saved === 'outlook') return saved;
    } catch (error) {}
    return 'apple';
}

function setCalendarPlatform(nextPlatform) {
    calendarPlatform = nextPlatform === 'google' || nextPlatform === 'outlook' ? nextPlatform : 'apple';
    try {
        localStorage.setItem(CALENDAR_PLATFORM_KEY, calendarPlatform);
    } catch (error) {}
    renderCalendarSubscription();
}

function loadRevealedCalendarProfileIds() {
    try {
        const saved = JSON.parse(localStorage.getItem(CALENDAR_REVEALED_PROFILES_KEY) || '[]');
        return new Set(Array.isArray(saved) ? saved : []);
    } catch (error) {
        return new Set();
    }
}

function persistRevealedCalendarProfileIds() {
    try {
        localStorage.setItem(
            CALENDAR_REVEALED_PROFILES_KEY,
            JSON.stringify(Array.from(revealedCalendarProfileIds))
        );
    } catch (error) {}
}

function getSelectedCalendarProfile() {
    return (calendarSubscriptionState.profiles || []).find((profile) => profile.selected) || null;
}

function toggleCalendarProfileReveal(profileId) {
    if (!profileId) return;
    if (revealedCalendarProfileIds.has(profileId)) revealedCalendarProfileIds.delete(profileId);
    else revealedCalendarProfileIds.add(profileId);
    persistRevealedCalendarProfileIds();
    renderCalendarSubscription();
}

function formatCalendarDateTime(value, fallback) {
    if (!value) return escapeHtml(fallback);
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return escapeHtml(value);
    return escapeHtml(
        formatUiDateCapitalized(parsed, {
            day: 'numeric',
            month: 'short',
            hour: '2-digit',
            minute: '2-digit'
        })
    );
}

function getCalendarCurrentViewModules() {
    if (currentEntity?.type !== 'group') return [];
    return Array.from(selectedModules || []);
}

function getCalendarCurrentViewSummary() {
    if (!currentEntity?.id) {
        return escapeHtml(t('schedule.calendar.currentView.empty', 'Open a schedule first to save the current page as a separate feed.'));
    }

    const modules = getCalendarCurrentViewModules();
    const modulesLabel = allAvailableModules.length === 0
        ? escapeHtml(t('schedule.calendar.currentView.noModules', 'No module filter on this page'))
        : modules.length === allAvailableModules.length
            ? escapeHtml(t('schedule.calendar.currentView.allModules', 'All modules selected'))
            : escapeHtml(
                t(
                    'schedule.calendar.currentView.someModules',
                    '{count} module(s) selected',
                    { count: modules.length }
                )
            );

    return `${escapeHtml(currentEntity.name)} · ${modulesLabel}`;
}

function getCalendarCacheStatusLabel(status) {
    if (status === 'cached') return escapeHtml(t('schedule.calendar.health.cached', 'Cached sources ready'));
    if (status === 'partial-cache') return escapeHtml(t('schedule.calendar.health.partial', 'Partially cached'));
    return escapeHtml(t('schedule.calendar.health.empty', 'No cached lessons yet'));
}

function getCalendarPlatformInstructions(profile) {
    const httpUrl = profile?.links?.http_url || '';
    const webcalUrl = profile?.links?.webcal_url || '';

    if (calendarPlatform === 'google') {
        return `
            <p>${escapeHtml(t('schedule.calendar.platform.google', 'Open Google Calendar on the web, choose Other calendars, then Add by URL and paste the HTTPS feed link.'))}</p>
            <code class="mt-2 block break-all rounded-2xl border border-slate-200 bg-white px-3 py-2 text-[11px] text-slate-600">${escapeHtml(httpUrl)}</code>
        `;
    }

    if (calendarPlatform === 'outlook') {
        return `
            <p>${escapeHtml(t('schedule.calendar.platform.outlook', 'In Outlook, use Add calendar or Subscribe from web, then paste the HTTPS feed link and confirm the subscription.'))}</p>
            <code class="mt-2 block break-all rounded-2xl border border-slate-200 bg-white px-3 py-2 text-[11px] text-slate-600">${escapeHtml(httpUrl)}</code>
        `;
    }

    return `
        <p>${escapeHtml(t('schedule.calendar.platform.apple', 'Use the Apple button below or paste the webcal link into Apple Calendar on iPhone, iPad, or Mac.'))}</p>
        <code class="mt-2 block break-all rounded-2xl border border-slate-200 bg-white px-3 py-2 text-[11px] text-slate-600">${escapeHtml(webcalUrl)}</code>
    `;
}

function renderCalendarSubscription() {
    const container = document.getElementById('calendarSubscriptionSection');
    if (!container) return;

    if (!scheduleAuthUser) {
        container.classList.add('hidden');
        container.innerHTML = '';
        return;
    }

    container.classList.remove('hidden');
    const selectedProfile = getSelectedCalendarProfile();
    const isProfileRevealed = selectedProfile ? revealedCalendarProfileIds.has(selectedProfile.id) : false;
    const syncReady = Boolean(calendarSubscriptionState.enabled);
    const syncPaused = !calendarSubscriptionState.sync_enabled;
    const title = escapeHtml(t('schedule.calendar.title', 'Calendar subscription'));
    const summary = syncReady
        ? escapeHtml(t('schedule.calendar.summaryReady', 'Private iCal feeds for your website sync profiles.'))
        : syncPaused
            ? escapeHtml(t('schedule.calendar.summaryPaused', 'Your calendar links are paused until you enable sync again.'))
            : escapeHtml(t('schedule.calendar.summarySetup', 'Build private feeds for all classes, exams only, or the current schedule page.'));
    const badgeText = syncReady
        ? escapeHtml(t('schedule.calendar.statusReady', 'Ready'))
        : syncPaused
            ? escapeHtml(t('schedule.calendar.statusPaused', 'Paused'))
            : escapeHtml(t('schedule.calendar.statusSetup', 'Setup'));
    const badgeClass = syncReady
        ? 'border-emerald-200 bg-emerald-100 text-emerald-700'
        : syncPaused
            ? 'border-slate-200 bg-slate-200 text-slate-700'
            : 'border-amber-200 bg-amber-100 text-amber-700';
    const toggleText = escapeHtml(
        t(
            isCalendarSubscriptionCollapsed ? 'schedule.calendar.expand' : 'schedule.calendar.collapse',
            isCalendarSubscriptionCollapsed ? 'Expand' : 'Collapse'
        )
    );

    if (calendarSubscriptionState.loading) {
        container.innerHTML = `
            <div class="rounded-3xl border border-emerald-100 bg-gradient-to-br from-emerald-50 via-white to-cyan-50 p-4 shadow-sm md:p-6">
                <div class="text-[11px] font-black uppercase tracking-[0.25em] text-emerald-500">${escapeHtml(t('schedule.calendar.eyebrow', 'Sync'))}</div>
                <div class="mt-2 flex flex-wrap items-center gap-2">
                    <h2 class="text-lg font-black tracking-tight text-slate-900 md:text-xl">${title}</h2>
                    <span class="inline-flex items-center rounded-full border px-2.5 py-1 text-[10px] font-black uppercase tracking-[0.18em] ${badgeClass}">${badgeText}</span>
                </div>
                <div class="mt-4 rounded-2xl border border-slate-200 bg-white/90 px-4 py-3 text-sm font-medium text-slate-500">
                    ${escapeHtml(t('schedule.calendar.loading', 'Loading your calendar profiles...'))}
                </div>
            </div>
        `;
        return;
    }

    const eligibilityNotice = calendarSubscriptionState.hasError
        ? `
            <div class="rounded-2xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-600">
                ${escapeHtml(t('schedule.calendar.error', 'Failed to load the calendar subscription.'))}
            </div>
            <button type="button"
                    onclick="refreshCalendarSubscription()"
                    class="inline-flex items-center justify-center rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700 transition-colors hover:border-blue-200 hover:text-blue-600">
                ${escapeHtml(t('schedule.action.retry', 'Retry'))}
            </button>
        `
        : !calendarSubscriptionState.eligibility.available
            ? `
                <div class="rounded-2xl border border-amber-100 bg-amber-50 px-4 py-3 text-sm text-amber-700">
                    ${escapeHtml(calendarSubscriptionState.eligibility.detail || t('schedule.calendar.unavailable', 'Calendar subscription is available for Telegram-linked accounts with bot schedule subscriptions.'))}
                </div>
            `
            : syncPaused
                ? `
                    <div class="rounded-2xl border border-slate-200 bg-slate-100 px-4 py-3 text-sm text-slate-700">
                        ${escapeHtml(t('schedule.calendar.pausedNotice', 'Sync is paused. External calendar apps will stop updating until you enable the feed again.'))}
                    </div>
                `
                : calendarSubscriptionState.justReset
                    ? `
                        <div class="rounded-2xl border border-emerald-100 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
                            ${escapeHtml(t('schedule.calendar.resetDone', 'The subscription link was updated. The previous link is now disabled.'))}
                        </div>
                    `
                    : '';

    const profileButtons = (calendarSubscriptionState.profiles || []).map((profile) => `
        <button type="button"
                onclick="selectCalendarSubscriptionProfile('${escapeJsString(profile.id)}')"
                class="inline-flex items-center gap-2 rounded-full border px-3 py-2 text-xs font-bold transition-colors ${profile.selected ? 'border-slate-900 bg-slate-900 text-white' : 'border-slate-200 bg-white text-slate-600 hover:border-blue-200 hover:text-blue-600'}">
            <span>${escapeHtml(profile.name)}</span>
            <span class="rounded-full px-2 py-0.5 text-[10px] uppercase tracking-[0.15em] ${profile.selected ? 'bg-white/15 text-white' : 'bg-slate-100 text-slate-400'}">${escapeHtml(profile.kind === 'custom' ? t('schedule.calendar.profile.custom', 'Preset') : t('schedule.calendar.profile.builtin', 'Built-in'))}</span>
        </button>
    `).join('');

    const visibleLink = selectedProfile
        ? (isProfileRevealed ? selectedProfile.links.http_url : selectedProfile.links.masked_http_url)
        : '';
    const modulesLabel = selectedProfile?.modules?.length
        ? escapeHtml(selectedProfile.modules.join(', '))
        : escapeHtml(t('schedule.calendar.meta.modulesAll', 'No module restriction'));

    const profileDetailsHtml = selectedProfile
        ? `
            <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                <div class="rounded-2xl border border-slate-200 bg-white/85 p-4">
                    <div class="text-[11px] font-black uppercase tracking-[0.18em] text-slate-400">${escapeHtml(t('schedule.calendar.urlLabel', 'Subscription URL'))}</div>
                    <code class="mt-2 block break-all text-xs font-medium text-slate-700">${escapeHtml(visibleLink || '')}</code>
                </div>
                <div class="rounded-2xl border border-slate-200 bg-white/85 p-4">
                    <div class="text-[11px] font-black uppercase tracking-[0.18em] text-slate-400">${escapeHtml(t('schedule.calendar.meta.scope', 'Scope'))}</div>
                    <div class="mt-2 text-sm font-semibold text-slate-800">${escapeHtml(selectedProfile.scope_label || selectedProfile.name)}</div>
                </div>
                <div class="rounded-2xl border border-slate-200 bg-white/85 p-4">
                    <div class="text-[11px] font-black uppercase tracking-[0.18em] text-slate-400">${escapeHtml(t('schedule.calendar.meta.modules', 'Modules'))}</div>
                    <div class="mt-2 text-sm font-semibold text-slate-800">${modulesLabel}</div>
                </div>
                <div class="rounded-2xl border border-slate-200 bg-white/85 p-4">
                    <div class="text-[11px] font-black uppercase tracking-[0.18em] text-slate-400">${escapeHtml(t('schedule.calendar.meta.events', 'Events in feed'))}</div>
                    <div class="mt-2 text-sm font-semibold text-slate-800">${escapeHtml(String(selectedProfile.health.event_count || 0))}</div>
                </div>
                <div class="rounded-2xl border border-slate-200 bg-white/85 p-4">
                    <div class="text-[11px] font-black uppercase tracking-[0.18em] text-slate-400">${escapeHtml(t('schedule.calendar.meta.next', 'Next event'))}</div>
                    <div class="mt-2 text-sm font-semibold text-slate-800">${selectedProfile.health.next_event_label ? escapeHtml(selectedProfile.health.next_event_label) : escapeHtml(t('schedule.calendar.meta.none', 'No upcoming event in range'))}</div>
                    <div class="mt-1 text-xs text-slate-500">${formatCalendarDateTime(selectedProfile.health.next_event_at, t('schedule.calendar.meta.none', 'No upcoming event in range'))}</div>
                </div>
                <div class="rounded-2xl border border-slate-200 bg-white/85 p-4">
                    <div class="text-[11px] font-black uppercase tracking-[0.18em] text-slate-400">${escapeHtml(t('schedule.calendar.meta.health', 'Feed health'))}</div>
                    <div class="mt-2 text-sm font-semibold text-slate-800">${getCalendarCacheStatusLabel(selectedProfile.health.cache_status)}</div>
                    <div class="mt-1 text-xs text-slate-500">${escapeHtml(t('schedule.calendar.meta.sources', '{used}/{total} cached source(s)', { used: selectedProfile.health.used_cached_sources || 0, total: selectedProfile.health.total_sources || 0 }))}</div>
                </div>
                <div class="rounded-2xl border border-slate-200 bg-white/85 p-4">
                    <div class="text-[11px] font-black uppercase tracking-[0.18em] text-slate-400">${escapeHtml(t('schedule.calendar.meta.updated', 'Source updated'))}</div>
                    <div class="mt-2 text-sm font-semibold text-slate-800">${formatCalendarDateTime(selectedProfile.health.source_updated_at, t('schedule.calendar.meta.never', 'Not yet'))}</div>
                </div>
                <div class="rounded-2xl border border-slate-200 bg-white/85 p-4">
                    <div class="text-[11px] font-black uppercase tracking-[0.18em] text-slate-400">${escapeHtml(t('schedule.calendar.meta.accessed', 'Last external access'))}</div>
                    <div class="mt-2 text-sm font-semibold text-slate-800">${formatCalendarDateTime(selectedProfile.health.last_accessed_at, t('schedule.calendar.meta.never', 'Not yet'))}</div>
                </div>
                <div class="rounded-2xl border border-slate-200 bg-white/85 p-4">
                    <div class="text-[11px] font-black uppercase tracking-[0.18em] text-slate-400">${escapeHtml(t('schedule.calendar.meta.generated', 'Preview generated'))}</div>
                    <div class="mt-2 text-sm font-semibold text-slate-800">${formatCalendarDateTime(selectedProfile.health.last_generated_at, t('schedule.calendar.meta.never', 'Not yet'))}</div>
                </div>
            </div>
        `
        : '';

    const canUseLinks = Boolean(calendarSubscriptionState.sync_enabled && selectedProfile?.links?.http_url);

    const actionButtonsHtml = selectedProfile ? `
        <div class="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
            <button type="button" ${canUseLinks ? '' : 'disabled'}
                    onclick="copyCalendarSubscriptionLink(event)"
                    class="inline-flex items-center justify-center rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-semibold transition-colors ${canUseLinks ? 'text-slate-700 hover:border-blue-200 hover:text-blue-600' : 'cursor-not-allowed text-slate-400'}">
                ${escapeHtml(t('schedule.calendar.copy', 'Copy link'))}
            </button>
            <button type="button"
                    onclick="toggleCalendarProfileReveal('${escapeJsString(selectedProfile.id)}')"
                    class="inline-flex items-center justify-center rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700 transition-colors hover:border-blue-200 hover:text-blue-600">
                ${escapeHtml(isProfileRevealed ? t('schedule.calendar.hide', 'Hide link') : t('schedule.calendar.reveal', 'Reveal link'))}
            </button>
            <button type="button" ${canUseLinks ? '' : 'disabled'}
                    onclick="openCalendarProfileLink('webcal')"
                    class="inline-flex items-center justify-center rounded-xl border border-blue-200 bg-blue-600 px-4 py-2 text-sm font-semibold text-white transition-colors ${canUseLinks ? 'hover:bg-blue-700' : 'cursor-not-allowed opacity-60'}">
                ${escapeHtml(t('schedule.calendar.apple', 'Open on iOS / Mac'))}
            </button>
            <button type="button" ${canUseLinks ? '' : 'disabled'}
                    onclick="openCalendarProfileLink('preview')"
                    class="inline-flex items-center justify-center rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-semibold transition-colors ${canUseLinks ? 'text-slate-700 hover:border-blue-200 hover:text-blue-600' : 'cursor-not-allowed text-slate-400'}">
                ${escapeHtml(t('schedule.calendar.preview', 'Test feed'))}
            </button>
            <button type="button" ${canUseLinks ? '' : 'disabled'}
                    onclick="openCalendarProfileLink('download')"
                    class="inline-flex items-center justify-center rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-semibold transition-colors ${canUseLinks ? 'text-slate-700 hover:border-blue-200 hover:text-blue-600' : 'cursor-not-allowed text-slate-400'}">
                ${escapeHtml(t('schedule.calendar.download', 'Download .ics'))}
            </button>
            <button type="button"
                    onclick="toggleCalendarSync(!calendarSubscriptionState.sync_enabled)"
                    class="inline-flex items-center justify-center rounded-xl border border-slate-200 bg-slate-100 px-4 py-2 text-sm font-semibold text-slate-700 transition-colors hover:border-slate-300 hover:bg-slate-200">
                ${escapeHtml(calendarSubscriptionState.sync_enabled ? t('schedule.calendar.disable', 'Disable sync') : t('schedule.calendar.enable', 'Enable sync'))}
            </button>
            <button type="button"
                    onclick="resetCalendarSubscription()"
                    class="inline-flex items-center justify-center rounded-xl border border-slate-200 bg-slate-100 px-4 py-2 text-sm font-semibold text-slate-700 transition-colors hover:border-slate-300 hover:bg-slate-200">
                ${escapeHtml(t('schedule.calendar.reset', 'Reset link'))}
            </button>
            ${selectedProfile.can_delete ? `
                <button type="button"
                        onclick="deleteCalendarSubscriptionProfile('${escapeJsString(selectedProfile.id)}')"
                        class="inline-flex items-center justify-center rounded-xl border border-red-100 bg-red-50 px-4 py-2 text-sm font-semibold text-red-600 transition-colors hover:bg-red-100">
                    ${escapeHtml(t('schedule.calendar.delete', 'Delete preset'))}
                </button>
            ` : ''}
        </div>
    ` : '';

    const platformTabsHtml = selectedProfile ? `
        <div class="rounded-2xl border border-slate-200 bg-white/85 p-4">
            <div class="text-[11px] font-black uppercase tracking-[0.18em] text-slate-400">${escapeHtml(t('schedule.calendar.instructionsTitle', 'How to subscribe'))}</div>
            <div class="mt-3 flex flex-wrap gap-2">
                ${['apple', 'google', 'outlook'].map((platform) => `
                    <button type="button"
                            onclick="setCalendarPlatform('${platform}')"
                            class="inline-flex items-center rounded-full border px-3 py-2 text-xs font-bold transition-colors ${calendarPlatform === platform ? 'border-slate-900 bg-slate-900 text-white' : 'border-slate-200 bg-white text-slate-600 hover:border-blue-200 hover:text-blue-600'}">
                        ${escapeHtml(t(`schedule.calendar.platform.${platform}.label`, platform.charAt(0).toUpperCase() + platform.slice(1)))}
                    </button>
                `).join('')}
            </div>
            <div class="mt-4 text-sm leading-6 text-slate-600">${getCalendarPlatformInstructions(selectedProfile)}</div>
        </div>
    ` : '';

    const currentViewCardHtml = `
        <div class="rounded-2xl border border-slate-200 bg-white/85 p-4">
            <div class="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
                <div class="min-w-0">
                    <div class="text-[11px] font-black uppercase tracking-[0.18em] text-slate-400">${escapeHtml(t('schedule.calendar.currentView.title', 'Current page preset'))}</div>
                    <div class="mt-2 text-sm font-semibold text-slate-800">${getCalendarCurrentViewSummary()}</div>
                    <p class="mt-2 text-xs leading-5 text-slate-500">${escapeHtml(t('schedule.calendar.currentView.description', 'Save the current website schedule page as a separate iCal feed. This sync config is stored on the website and does not reuse Telegram quick filters.'))}</p>
                </div>
                <div class="flex flex-col gap-2 sm:flex-row sm:items-center">
                    <select id="calendarCurrentViewMode" onchange="window.calendarCurrentViewMode=this.value" class="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700">
                        <option value="all" ${window.calendarCurrentViewMode === 'all' ? 'selected' : ''}>${escapeHtml(t('schedule.calendar.mode.all', 'All classes'))}</option>
                        <option value="exams_only" ${window.calendarCurrentViewMode === 'exams_only' ? 'selected' : ''}>${escapeHtml(t('schedule.calendar.mode.exams', 'Exams only'))}</option>
                    </select>
                    <button type="button" ${currentEntity?.id ? '' : 'disabled'}
                            onclick="createCalendarProfileFromCurrentView()"
                            class="inline-flex items-center justify-center rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-semibold transition-colors ${currentEntity?.id ? 'text-slate-700 hover:border-blue-200 hover:text-blue-600' : 'cursor-not-allowed text-slate-400'}">
                        ${escapeHtml(t('schedule.calendar.currentView.save', 'Save current view'))}
                    </button>
                </div>
            </div>
        </div>
    `;

    const panelBodyHtml = isCalendarSubscriptionCollapsed ? '' : `
        <div class="mt-4 flex flex-col gap-4 border-t border-emerald-100 pt-4">
            <p class="max-w-3xl text-sm leading-6 text-slate-600">${summary}</p>
            ${eligibilityNotice}
            <div class="grid gap-3 md:grid-cols-3">
                <div class="rounded-2xl border border-slate-200 bg-white/85 p-4">
                    <div class="text-[11px] font-black uppercase tracking-[0.18em] text-slate-400">${escapeHtml(t('schedule.calendar.setting.source.label', 'Source'))}</div>
                    <div class="mt-2 text-sm font-semibold text-slate-800">${escapeHtml(t('schedule.calendar.setting.source.value', 'Active Telegram schedule subscriptions'))}</div>
                </div>
                <div class="rounded-2xl border border-slate-200 bg-white/85 p-4">
                    <div class="text-[11px] font-black uppercase tracking-[0.18em] text-slate-400">${escapeHtml(t('schedule.calendar.setting.scope.label', 'Included right now'))}</div>
                    <div class="mt-2 text-sm font-semibold text-slate-800">${escapeHtml(t('schedule.calendar.setting.scope.currentValue', '{subs} subscription(s), {entities} unique source(s)', { subs: calendarSubscriptionState.source_summary.active_subscriptions || 0, entities: calendarSubscriptionState.source_summary.active_entities || 0 }))}</div>
                </div>
                <div class="rounded-2xl border border-slate-200 bg-white/85 p-4">
                    <div class="text-[11px] font-black uppercase tracking-[0.18em] text-slate-400">${escapeHtml(t('schedule.calendar.setting.window.label', 'Time window'))}</div>
                    <div class="mt-2 text-sm font-semibold text-slate-800">${escapeHtml(t('schedule.calendar.setting.window.value', 'Recent 14 days and the next 90 days of cached schedule data'))}</div>
                </div>
            </div>
            <div class="flex flex-wrap gap-2">${profileButtons}</div>
            ${profileDetailsHtml}
            ${actionButtonsHtml}
            ${platformTabsHtml}
            ${currentViewCardHtml}
        </div>
    `;

    container.innerHTML = `
        <div class="rounded-3xl border border-emerald-100 bg-gradient-to-br from-emerald-50 via-white to-cyan-50 p-4 shadow-sm md:p-6">
            <div class="text-[11px] font-black uppercase tracking-[0.25em] text-emerald-500">${escapeHtml(t('schedule.calendar.eyebrow', 'Sync'))}</div>
            <button type="button" onclick="toggleCalendarSubscriptionSection()" class="mt-2 flex w-full items-start justify-between gap-4 text-left">
                <div class="min-w-0">
                    <div class="flex flex-wrap items-center gap-2">
                        <h2 class="text-lg font-black tracking-tight text-slate-900 md:text-xl">${title}</h2>
                        <span class="inline-flex items-center rounded-full border px-2.5 py-1 text-[10px] font-black uppercase tracking-[0.18em] ${badgeClass}">${badgeText}</span>
                    </div>
                    <p class="mt-2 max-w-3xl text-sm leading-6 text-slate-600">${summary}</p>
                </div>
                <span class="inline-flex shrink-0 items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-2 text-xs font-bold text-slate-600 shadow-sm">
                    ${toggleText}
                    <svg class="h-4 w-4 transition-transform ${isCalendarSubscriptionCollapsed ? '' : 'rotate-180'}" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path>
                    </svg>
                </span>
            </button>
            ${panelBodyHtml}
        </div>
    `;
}

function applyCalendarSubscriptionPayload(data, { justReset = false } = {}) {
    calendarSubscriptionState = {
        ...createDefaultCalendarSubscriptionState(),
        ...data,
        loading: false,
        hasError: false,
        justReset
    };
}

async function parseCalendarError(response) {
    try {
        const data = await response.json();
        return data?.detail || `HTTP ${response.status}`;
    } catch (error) {
        return `HTTP ${response.status}`;
    }
}

async function refreshCalendarSubscription() {
    if (!scheduleAuthUser) {
        calendarSubscriptionState = createDefaultCalendarSubscriptionState();
        renderCalendarSubscription();
        return;
    }

    const token = localStorage.getItem('jwt_token');
    if (!token) {
        scheduleAuthUser = null;
        calendarSubscriptionState = createDefaultCalendarSubscriptionState();
        renderCalendarSubscription();
        return;
    }

    calendarSubscriptionState = { ...calendarSubscriptionState, loading: true, hasError: false, justReset: false };
    renderCalendarSubscription();

    try {
        const response = await fetch(`${API_BASE}/cal/subscription`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });

        if (response.status === 401) {
            scheduleAuthUser = null;
            calendarSubscriptionState = createDefaultCalendarSubscriptionState();
            renderCalendarSubscription();
            return;
        }

        if (!response.ok) throw new Error(await parseCalendarError(response));
        applyCalendarSubscriptionPayload(await response.json());
    } catch (error) {
        console.error('Failed to load calendar subscription', error);
        calendarSubscriptionState = { ...createDefaultCalendarSubscriptionState(), hasError: true };
    }

    renderCalendarSubscription();
}

function copyCalendarSubscriptionLink(event) {
    const selectedProfile = getSelectedCalendarProfile();
    if (!selectedProfile?.links?.http_url || !calendarSubscriptionState.sync_enabled) return;
    copyToClipboard(selectedProfile.links.http_url, event);
}

function openCalendarProfileLink(kind) {
    const selectedProfile = getSelectedCalendarProfile();
    if (!selectedProfile || !calendarSubscriptionState.sync_enabled) return;

    const targetUrl = kind === 'download'
        ? selectedProfile.links.download_url
        : kind === 'webcal'
            ? selectedProfile.links.webcal_url
            : selectedProfile.links.preview_url;

    if (!targetUrl) return;
    if (kind === 'webcal') window.location.href = targetUrl;
    else window.open(targetUrl, '_blank', 'noopener');
}

async function performCalendarMutation(url, options = {}, { justReset = false } = {}) {
    const token = localStorage.getItem('jwt_token');
    if (!token) {
        scheduleAuthUser = null;
        calendarSubscriptionState = createDefaultCalendarSubscriptionState();
        renderCalendarSubscription();
        return null;
    }

    calendarSubscriptionState = { ...calendarSubscriptionState, loading: true, hasError: false, justReset: false };
    renderCalendarSubscription();

    try {
        const response = await fetch(url, {
            ...options,
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`,
                ...(options.headers || {})
            }
        });

        if (response.status === 401) {
            scheduleAuthUser = null;
            calendarSubscriptionState = createDefaultCalendarSubscriptionState();
            renderCalendarSubscription();
            return null;
        }

        if (!response.ok) {
            const detail = await parseCalendarError(response);
            throw new Error(detail);
        }

        applyCalendarSubscriptionPayload(await response.json(), { justReset });
        renderCalendarSubscription();
        return calendarSubscriptionState;
    } catch (error) {
        console.error('Calendar mutation failed', error);
        calendarSubscriptionState = { ...createDefaultCalendarSubscriptionState(), hasError: true };
        renderCalendarSubscription();
        window.alert(error.message || t('schedule.calendar.error', 'Failed to load the calendar subscription.'));
        return null;
    }
}

async function resetCalendarSubscription() {
    if (!window.confirm(t('schedule.calendar.confirmReset', 'Reset the private calendar link? The previous URL will stop working immediately.'))) return;
    await performCalendarMutation(`${API_BASE}/cal/subscription/reset`, { method: 'POST' }, { justReset: true });
}

async function toggleCalendarSync(enabled) {
    const confirmKey = enabled ? 'schedule.calendar.confirmEnable' : 'schedule.calendar.confirmDisable';
    const fallback = enabled
        ? 'Enable sync again for all of your website calendar feeds?'
        : 'Disable sync for all of your website calendar feeds? Existing external subscriptions will stop updating.';
    if (!window.confirm(t(confirmKey, fallback))) return;

    await performCalendarMutation(`${API_BASE}/cal/subscription/toggle`, {
        method: 'POST',
        body: JSON.stringify({ enabled })
    });
}

async function selectCalendarSubscriptionProfile(profileId) {
    if (!profileId || profileId === calendarSubscriptionState.selected_profile_id) return;
    await performCalendarMutation(`${API_BASE}/cal/subscription/select`, {
        method: 'POST',
        body: JSON.stringify({ profile_id: profileId })
    });
}

async function createCalendarProfileFromCurrentView() {
    if (!currentEntity?.id) return;

    await performCalendarMutation(`${API_BASE}/cal/subscription/profiles`, {
        method: 'POST',
        body: JSON.stringify({
            entity_type: currentEntity.type,
            entity_id: currentEntity.id,
            entity_name: currentEntity.name,
            lesson_mode: window.calendarCurrentViewMode,
            modules: getCalendarCurrentViewModules()
        })
    });
}

async function deleteCalendarSubscriptionProfile(profileId) {
    if (!window.confirm(t('schedule.calendar.confirmDelete', 'Delete this saved website calendar preset?'))) return;
    await performCalendarMutation(`${API_BASE}/cal/subscription/profiles/${encodeURIComponent(profileId)}`, {
        method: 'DELETE'
    });
}

const originalLoadSchedule = loadSchedule;
loadSchedule = async function(...args) {
    try {
        return await originalLoadSchedule(...args);
    } finally {
        renderCalendarSubscription();
    }
};

const originalToggleModule = toggleModule;
toggleModule = function(...args) {
    originalToggleModule(...args);
    renderCalendarSubscription();
};

const originalSelectAllModules = selectAllModules;
selectAllModules = function(...args) {
    originalSelectAllModules(...args);
    renderCalendarSubscription();
};

const originalClearAllModules = clearAllModules;
clearAllModules = function(...args) {
    originalClearAllModules(...args);
    renderCalendarSubscription();
};
