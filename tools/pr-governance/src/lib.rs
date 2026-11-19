//! Standalone, fail-closed time-windowed pull-request review evaluator.
//! Source data MUST be independently authenticated by a trusted GitHub App.
//! This pure library does not alter GitHub permissions, rules, or merge status.
use std::collections::{BTreeMap, BTreeSet};

pub const ORESOFTWARE: u64 = 11_139_560;
pub const THE1MILLS: u64 = 2_148_448;
pub const THREE_DAYS: u64 = 72 * 60 * 60;
pub const TEN_DAYS: u64 = 240 * 60 * 60;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ReviewState { Approved, ChangesRequested, Commented, Dismissed }
#[derive(Clone, Debug)]
pub struct HumanReview {
    pub actor_id: u64,
    pub review_id: u64,
    pub submitted_at: u64,
    pub head_sha: String,
    pub state: ReviewState,
    pub has_write_access: bool,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub enum AiProvider { OpenAi, Anthropic }
#[derive(Clone, Debug)]
pub struct AiReview {
    pub review_id: u64,
    pub published_at: u64,
    pub provider: AiProvider,
    pub head_sha: String,
    pub succeeded: bool,
    /// This MUST be asserted only by an authenticated, trusted integration.
    pub verified_source: bool,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CiState { Success, Failure, Pending, Skipped, Neutral }
#[derive(Clone, Debug)]
pub struct RequiredCi { pub name: String, pub app_id: u64 }
#[derive(Clone, Debug)]
pub struct CiRun {
    pub name: String,
    pub app_id: u64,
    pub head_sha: String,
    pub state: CiState,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ReviewWindow { Draft, StrictInitial, Accelerated, StrictRenewed }
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ReadinessState { Draft, Ready }
#[derive(Clone, Debug)]
pub struct ReadinessEvent {
    pub event_id: u64,
    pub at: u64,
    pub state: ReadinessState,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum OverlapDisposition { Incorporated, Updated, Superseded, Independent, Unresolved }
#[derive(Clone, Debug)]
pub struct OverlapCandidate {
    pub repository: String,
    pub pr_number: u64,
    pub disposition: OverlapDisposition,
    pub rationale: String,
}
#[derive(Clone, Debug)]
pub struct OverlapAudit {
    pub head_sha: String,
    pub completed_at: u64,
    /// The trusted integration increments this for changes to relevant open PRs.
    pub open_pr_index_version: u64,
    pub verified_source: bool,
    pub candidates: Vec<OverlapCandidate>,
}
#[derive(Clone, Debug)]
pub struct Facts {
    pub repository_id: u64,
    pub pr_number: u64,
    /// Immutable creation time. Only starts the review clock if initially Ready.
    pub created_at: u64,
    pub created_as_draft: bool,
    /// Complete, authenticated GitHub lifecycle timeline (initial state + all transitions).
    pub lifecycle_complete: bool,
    pub readiness_events: Vec<ReadinessEvent>,
    pub now: u64,
    pub author_id: u64,
    pub head_sha: String,
    pub draft: bool,
    /// Labels are normalized lowercase and fetched immediately before the action.
    pub labels_verified: bool,
    pub labels: Vec<String>,
    /// Integration-attested reviewability of draft content; not a CI pass.
    pub draft_work_complete: bool,
    /// Authenticated open-PR-index snapshot epoch (never supplied by the PR author).
    pub open_pr_index_version: u64,
    pub overlap_audit: Option<OverlapAudit>,
    /// These attestations MUST come from authenticated live GitHub state.
    pub mergeable: bool,
    pub on_hold: bool,
    pub critical_risk: bool,
    pub github_rules_satisfied: bool,
    pub human_reviews: Vec<HumanReview>,
    pub ai_reviews: Vec<AiReview>,
    pub required_ci: Vec<RequiredCi>,
    pub ci_runs: Vec<CiRun>,
}
#[derive(Debug)]
pub struct Decision {
    pub pass: bool,
    pub window: ReviewWindow,
    pub blockers: Vec<String>,
}
fn valid_git_oid(oid: &str) -> bool {
    (oid.len() == 40 || oid.len() == 64) && oid.as_bytes().iter().all(u8::is_ascii_hexdigit)
}

/// Derive the current review-cycle start. Never guess from creation time for a
/// formerly drafted PR or accept editable PR body / label timestamps.
pub fn ready_cycle_start(f: &Facts) -> Result<Option<u64>, &'static str> {
    if !f.lifecycle_complete { return Err("incomplete readiness lifecycle evidence"); }
    if f.now < f.created_at { return Err("future PR creation timestamp"); }
    let mut state = if f.created_as_draft {
        ReadinessState::Draft
    } else {
        ReadinessState::Ready
    };
    let mut since = if f.created_as_draft { None } else { Some(f.created_at) };
    let mut previous: Option<(u64, u64)> = None;
    let mut event_ids = BTreeSet::new();
    for event in &f.readiness_events {
        if event.event_id == 0 || !event_ids.insert(event.event_id)
            || event.at < f.created_at || event.at > f.now
            || previous.is_some_and(|prev| (event.at, event.event_id) <= prev)
            || event.state == state {
            return Err("invalid or contradictory readiness transition history");
        }
        previous = Some((event.at, event.event_id));
        state = event.state;
        since = if state == ReadinessState::Ready { Some(event.at) } else { None };
    }
    if f.draft != (state == ReadinessState::Draft) {
        return Err("current draft status disagrees with readiness timeline");
    }
    Ok(since)
}
fn has_draft_hold(f: &Facts) -> bool {
    f.labels.iter().any(|label| {
        label.eq_ignore_ascii_case("keep-draft") || label.eq_ignore_ascii_case("not-ready")
    })
}
fn check_overlap_audit(f: &Facts, since: u64, blockers: &mut Vec<String>) {
    let Some(audit) = &f.overlap_audit else {
        blockers.push("missing competing/overlapping PR audit".into());
        return;
    };
    if !audit.verified_source || audit.head_sha != f.head_sha
        || audit.completed_at < since || audit.completed_at > f.now
        || audit.open_pr_index_version == 0 || f.open_pr_index_version == 0
        || audit.open_pr_index_version != f.open_pr_index_version {
        blockers.push("stale, incomplete or unverified overlap audit".into());
    }
    let mut candidates = BTreeSet::new();
    for c in &audit.candidates {
        if c.repository.trim().is_empty() || c.pr_number == 0
            || !candidates.insert((c.repository.to_lowercase(), c.pr_number))
            || c.rationale.trim().is_empty() {
            blockers.push("invalid or duplicate overlap disposition evidence".into());
        }
        if c.disposition == OverlapDisposition::Unresolved {
            blockers.push(format!("unresolved competing PR: {}/{}", c.repository, c.pr_number));
        }
    }
}
pub fn review_window(ready_since: u64, now: u64) -> ReviewWindow {
    let age = now.saturating_sub(ready_since);
    if age < THREE_DAYS { ReviewWindow::StrictInitial }
    else if age < TEN_DAYS { ReviewWindow::Accelerated }
    else { ReviewWindow::StrictRenewed }
}
pub fn evaluate(f: &Facts) -> Decision {
    let mut blockers = Vec::<String>::new();
    let cycle = ready_cycle_start(f);
    if let Err(err) = &cycle { blockers.push((*err).into()); }
    let ready_since = cycle.ok().flatten();
    let window = ready_since.map_or(ReviewWindow::Draft, |start| review_window(start, f.now));
    if f.repository_id == 0 || f.pr_number == 0 || f.author_id == 0
        || !valid_git_oid(&f.head_sha) {
        blockers.push("invalid PR identity".into());
    }
    if f.now < f.created_at { blockers.push("future PR creation timestamp".into()); }
    if f.draft { blockers.push("draft PR".into()); }
    if !f.labels_verified { blockers.push("unverified PR labels".into()); }
    if has_draft_hold(f) { blockers.push("keep-draft/not-ready label prevents merge".into()); }
    if window == ReviewWindow::Accelerated {
        if let Some(start) = ready_since { check_overlap_audit(f, start, &mut blockers); }
    }
    if !f.mergeable { blockers.push("merge conflicts or unconfirmed mergeability".into()); }
    if f.on_hold { blockers.push("explicit hold".into()); }
    if f.critical_risk { blockers.push("critical safety risk".into()); }
    if !f.github_rules_satisfied { blockers.push("GitHub protections not satisfied".into()); }

    // CI must actually be green on the current head, in ALL review windows.
    if f.required_ci.is_empty() { blockers.push("no required CI configured".into()); }
    let mut required_names = BTreeSet::new();
    for required in &f.required_ci {
        if required.name.trim().is_empty() || required.app_id == 0
            || required.name == "review-policy" || !required_names.insert(&required.name) {
            blockers.push(format!("invalid required CI configuration: {}", required.name));
            continue;
        }
        let matches: Vec<_> = f.ci_runs.iter().filter(|r| {
            r.name == required.name && r.app_id == required.app_id
                && r.head_sha == f.head_sha
        }).collect();
        if matches.len() != 1 {
            blockers.push(format!("missing or ambiguous required CI: {}", required.name));
        } else if matches[0].state != CiState::Success {
            blockers.push(format!("required CI not successful: {}", required.name));
        }
        // Same-name, different-App CI cannot silently spoof a configured context.
        if f.ci_runs.iter().any(|r| r.name == required.name && r.head_sha == f.head_sha
            && r.app_id != required.app_id) {
            blockers.push(format!("conflicting CI provider for {}", required.name));
        }
    }

    let mut humans: BTreeMap<u64, &HumanReview> = BTreeMap::new();
    let mut human_ids = BTreeSet::new();
    for r in &f.human_reviews {
        if r.actor_id == 0 || r.review_id == 0 || !human_ids.insert(r.review_id)
            || r.submitted_at < f.created_at || r.submitted_at > f.now {
            blockers.push("invalid or duplicate human review evidence".into());
            continue;
        }
        if humans.get(&r.actor_id).is_none_or(|prev| {
            (r.submitted_at, r.review_id) > (prev.submitted_at, prev.review_id)
        }) { humans.insert(r.actor_id, r); }
    }
    if humans.values().any(|r| r.has_write_access && r.state == ReviewState::ChangesRequested) {
        blockers.push("unresolved changes requested".into());
    }
    let human_approved = |id: u64, since: u64| humans.get(&id).is_some_and(|r| {
        r.actor_id != f.author_id && r.has_write_access && r.head_sha == f.head_sha
            && r.state == ReviewState::Approved && r.submitted_at >= since
    });

    let mut ai: BTreeMap<AiProvider, &AiReview> = BTreeMap::new();
    let mut ai_ids = BTreeSet::new();
    for r in &f.ai_reviews {
        if r.review_id == 0 || !ai_ids.insert(r.review_id)
            || r.published_at < f.created_at || r.published_at > f.now {
            blockers.push("invalid or duplicate AI review evidence".into());
            continue;
        }
        if ai.get(&r.provider).is_none_or(|prev| {
            (r.published_at, r.review_id) > (prev.published_at, prev.review_id)
        }) { ai.insert(r.provider, r); }
    }
    let ai_approved = |provider: AiProvider, since: u64| ai.get(&provider).is_some_and(|r| {
        r.head_sha == f.head_sha && r.succeeded && r.verified_source
            && r.published_at >= since
    });

    match window {
        ReviewWindow::StrictInitial | ReviewWindow::StrictRenewed => {
            let start = ready_since.unwrap_or(f.created_at);
            let since = if window == ReviewWindow::StrictRenewed {
                start.saturating_add(TEN_DAYS)
            } else { start };
            for id in [ORESOFTWARE, THE1MILLS] {
                if !human_approved(id, since) {
                    blockers.push(format!("missing current, timely human approval from {}", id));
                }
            }
            for provider in [AiProvider::OpenAi, AiProvider::Anthropic] {
                if !ai_approved(provider, since) {
                    blockers.push(format!("missing current, timely {:?} approval", provider));
                }
            }
        }
        ReviewWindow::Accelerated => {
            let start = ready_since.unwrap_or(f.created_at);
            let any_human = humans.keys().any(|&id| human_approved(id, start));
            let any_ai = [AiProvider::OpenAi, AiProvider::Anthropic].iter()
                .copied().any(|p| ai_approved(p, start));
            if !any_human && !any_ai {
                blockers.push("fast lane requires one verified independent human or AI approval".into());
            }
        }
        ReviewWindow::Draft => {}
    }
    Decision { pass: blockers.is_empty(), window, blockers }
}

/// Advisory decision for an authorized draft recovery service, NOT a Ready
/// transition. No four-party reviews are required to *become* reviewable.
pub fn evaluate_draft_promotion(f: &Facts) -> (bool, Vec<String>) {
    let mut blockers = Vec::new();
    if !f.draft { blockers.push("PR is already ready".into()); }
    if let Err(err) = ready_cycle_start(f) { blockers.push(err.into()); }
    if !f.labels_verified { blockers.push("unverified PR labels".into()); }
    if has_draft_hold(f) { blockers.push("keep-draft/not-ready label blocks promotion".into()); }
    if f.on_hold || f.critical_risk { blockers.push("explicit hold or critical risk".into()); }
    if !f.mergeable { blockers.push("unresolved base-branch conflicts".into()); }
    if !f.draft_work_complete { blockers.push("draft implementation not ready".into()); }
    check_overlap_audit(f, f.created_at, &mut blockers);
    (blockers.is_empty(), blockers)
}

#[cfg(test)]
mod tests {
    use super::*;
    const T: u64 = 1_000_000;
    const SHA: &str = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    fn human(id: u64, at: u64) -> HumanReview {
        HumanReview { actor_id: id, review_id: id + at, submitted_at: at,
            head_sha: SHA.into(), state: ReviewState::Approved, has_write_access: true }
    }
    fn machine(provider: AiProvider, id: u64, at: u64) -> AiReview {
        AiReview { review_id: id, published_at: at, provider,
            head_sha: SHA.into(), succeeded: true, verified_source: true }
    }
    fn facts(age: u64) -> Facts {
        Facts { repository_id: 777, pr_number: 42, created_at: T,
            created_as_draft: false, lifecycle_complete: true, readiness_events: vec![],
            now: T + age, author_id: 999, head_sha: SHA.into(), draft: false,
            labels_verified: true, labels: vec![], draft_work_complete: true,
            open_pr_index_version: 1,
            overlap_audit: Some(OverlapAudit { head_sha: SHA.into(), completed_at: T,
                open_pr_index_version: 1, verified_source: true, candidates: vec![] }),
            mergeable: true, on_hold: false, critical_risk: false, github_rules_satisfied: true,
            human_reviews: vec![human(ORESOFTWARE, T + 1), human(THE1MILLS, T + 2)],
            ai_reviews: vec![machine(AiProvider::OpenAi, 11, T + 3),
                machine(AiProvider::Anthropic, 12, T + 4)],
            required_ci: vec![RequiredCi { name: "build".into(), app_id: 101 }],
            ci_runs: vec![CiRun { name: "build".into(), app_id: 101,
                head_sha: SHA.into(), state: CiState::Success }] }
    }
    #[test] fn initial_strict_all_four_pass() { assert!(evaluate(&facts(100)).pass); }
    #[test] fn before_72_requires_both_humans() {
        let mut f = facts(THREE_DAYS - 1); f.human_reviews.pop();
        assert!(!evaluate(&f).pass);
    }
    #[test] fn before_72_requires_both_ai_families() {
        let mut f = facts(THREE_DAYS - 1); f.ai_reviews.pop();
        assert!(!evaluate(&f).pass);
    }
    #[test] fn boundary_72_exactly_opens_fast_lane() {
        let mut f = facts(THREE_DAYS); f.human_reviews.clear(); f.ai_reviews.pop();
        assert_eq!(evaluate(&f).window, ReviewWindow::Accelerated);
        assert!(evaluate(&f).pass);
    }
    #[test] fn boundary_one_second_before_72_is_strict() {
        let mut f = facts(THREE_DAYS - 1); f.human_reviews.clear(); f.ai_reviews.pop();
        assert_eq!(evaluate(&f).window, ReviewWindow::StrictInitial);
        assert!(!evaluate(&f).pass);
    }
    #[test] fn fast_lane_one_human_any_write_capable() {
        let mut f = facts(THREE_DAYS + 1); f.human_reviews = vec![human(333, T + 7)]; f.ai_reviews.clear();
        assert!(evaluate(&f).pass);
    }
    #[test] fn fast_lane_one_verified_ai() {
        let mut f = facts(THREE_DAYS + 1); f.human_reviews.clear(); f.ai_reviews.pop();
        assert!(evaluate(&f).pass);
    }
    #[test] fn fast_lane_zero_approvals_fails() {
        let mut f = facts(THREE_DAYS + 1); f.human_reviews.clear(); f.ai_reviews.clear();
        assert!(!evaluate(&f).pass);
    }
    #[test] fn fast_lane_no_unverified_ai() {
        let mut f = facts(THREE_DAYS + 1); f.human_reviews.clear(); f.ai_reviews.pop();
        f.ai_reviews[0].verified_source = false;
        assert!(!evaluate(&f).pass);
    }
    #[test] fn fast_lane_no_author_self_approval() {
        let mut f = facts(THREE_DAYS + 1); f.author_id = 333;
        f.human_reviews = vec![human(333, T + 2)]; f.ai_reviews.clear();
        assert!(!evaluate(&f).pass);
    }
    #[test] fn final_second_of_fast_lane() {
        let mut f = facts(TEN_DAYS - 1); f.human_reviews.clear(); f.ai_reviews.pop();
        assert_eq!(evaluate(&f).window, ReviewWindow::Accelerated);
        assert!(evaluate(&f).pass);
    }
    #[test] fn exactly_ten_days_revokes_fast_lane() {
        let mut f = facts(TEN_DAYS); f.human_reviews.clear(); f.ai_reviews.pop();
        assert_eq!(evaluate(&f).window, ReviewWindow::StrictRenewed);
        assert!(!evaluate(&f).pass);
    }
    #[test] fn ten_day_old_four_reviews_not_fresh() {
        let f = facts(TEN_DAYS);
        assert!(!evaluate(&f).pass);
    }
    #[test] fn ten_day_fresh_all_four_pass() {
        let mut f = facts(TEN_DAYS);
        f.human_reviews = vec![human(ORESOFTWARE, T + TEN_DAYS),
            human(THE1MILLS, T + TEN_DAYS)];
        f.ai_reviews = vec![machine(AiProvider::OpenAi, 111, T + TEN_DAYS),
            machine(AiProvider::Anthropic, 112, T + TEN_DAYS)];
        assert!(evaluate(&f).pass);
    }
    #[test] fn ten_day_missing_one_renewed_review_fails() {
        let mut f = facts(TEN_DAYS + 10);
        f.human_reviews = vec![human(ORESOFTWARE, T + TEN_DAYS),
            human(THE1MILLS, T + TEN_DAYS)];
        f.ai_reviews = vec![machine(AiProvider::OpenAi, 111, T + TEN_DAYS)];
        assert!(!evaluate(&f).pass);
    }
    #[test] fn old_approvals_plus_one_new_not_enough_after_ten_days() {
        let mut f = facts(TEN_DAYS + 20);
        f.human_reviews.push(human(333, T + TEN_DAYS + 2));
        assert!(!evaluate(&f).pass);
    }
    #[test] fn changed_sha_invalidates_prior_reviews() {
        let mut f = facts(THREE_DAYS + 10); f.head_sha = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb".into();
        f.ci_runs[0].head_sha = f.head_sha.clone();
        assert!(!evaluate(&f).pass);
    }
    #[test] fn latest_rejection_blocks_accelerated() {
        let mut f = facts(THREE_DAYS + 10);
        f.human_reviews.push(HumanReview { actor_id: THE1MILLS, review_id: 9999,
            submitted_at: T + 11, head_sha: SHA.into(),
            state: ReviewState::ChangesRequested, has_write_access: true });
        assert!(!evaluate(&f).pass);
    }
    #[test] fn later_human_approval_clears_changes_requested() {
        let mut f = facts(THREE_DAYS + 10);
        f.human_reviews.push(HumanReview { actor_id: THE1MILLS, review_id: 9999,
            submitted_at: T + 11, head_sha: SHA.into(),
            state: ReviewState::ChangesRequested, has_write_access: true });
        f.human_reviews.push(human(THE1MILLS, T + 12));
        assert!(evaluate(&f).pass);
    }
    #[test] fn newer_failed_ai_cannot_reuse_prior_pass() {
        let mut f = facts(THREE_DAYS + 10); f.human_reviews.clear(); f.ai_reviews.pop();
        f.ai_reviews.push(AiReview {review_id: 88, published_at: T + 8,
            provider: AiProvider::OpenAi, head_sha: SHA.into(),
            succeeded: false, verified_source: true });
        assert!(!evaluate(&f).pass);
    }
    #[test] fn ci_failed_pending_skipped_neutral_all_block() {
        let mut f = facts(THREE_DAYS + 10);
        for state in [CiState::Failure, CiState::Pending, CiState::Skipped, CiState::Neutral] {
            f.ci_runs[0].state = state; assert!(!evaluate(&f).pass);
        }
    }
    #[test] fn missing_or_duplicate_ci_block() {
        let mut f = facts(THREE_DAYS + 10);
        f.ci_runs.clear(); assert!(!evaluate(&f).pass);
        f.ci_runs = facts(10).ci_runs;
        f.ci_runs.push(f.ci_runs[0].clone());
        assert!(!evaluate(&f).pass);
    }
    #[test] fn no_required_ci_and_circular_gate_block() {
        let mut f = facts(THREE_DAYS + 10);
        f.required_ci.clear(); assert!(!evaluate(&f).pass);
        f.required_ci = vec![RequiredCi { name: "review-policy".into(), app_id: 101 }];
        assert!(!evaluate(&f).pass);
    }
    #[test] fn wrong_ci_app_or_head_fails() {
        let mut f = facts(THREE_DAYS + 10); f.ci_runs[0].app_id = 102;
        assert!(!evaluate(&f).pass);
        f.ci_runs[0].app_id = 101; f.ci_runs[0].head_sha = "old".into();
        assert!(!evaluate(&f).pass);
    }
    #[test] fn contradictory_ci_context_blocks() {
        let mut f = facts(THREE_DAYS + 10);
        f.ci_runs.push(CiRun { name: "build".into(), app_id: 202, head_sha: SHA.into(),
            state: CiState::Success });
        assert!(!evaluate(&f).pass);
    }
    #[test] fn no_merge_on_conflicts_or_unknown_mergeability() {
        let mut f = facts(THREE_DAYS + 10); f.mergeable = false;
        assert!(!evaluate(&f).pass);
    }
    #[test] fn hold_security_and_rules_fail_closed() {
        let mut f = facts(THREE_DAYS + 10);
        f.on_hold = true; assert!(!evaluate(&f).pass);
        f.on_hold = false; f.critical_risk = true; assert!(!evaluate(&f).pass);
        f.critical_risk = false; f.github_rules_satisfied = false; assert!(!evaluate(&f).pass);
    }
    #[test] fn draft_and_future_timestamp_fail() {
        let mut f = facts(THREE_DAYS + 10); f.draft = true;
        assert!(!evaluate(&f).pass);
        f.draft = false; f.now = T - 1; assert!(!evaluate(&f).pass);
    }
    #[test] fn invalid_identity_fails_closed() {
        let mut f = facts(THREE_DAYS + 10); f.head_sha = "not_sha".into();
        assert!(!evaluate(&f).pass);
        f.head_sha = SHA.into(); f.repository_id = 0; assert!(!evaluate(&f).pass);
    }
    #[test] fn stale_or_duplicate_human_evidence_fails() {
        let mut f = facts(THREE_DAYS + 10);
        f.human_reviews[0].submitted_at = T - 1; assert!(!evaluate(&f).pass);
        f.human_reviews[0].submitted_at = T + 1;
        f.human_reviews.push(f.human_reviews[0].clone());
        assert!(!evaluate(&f).pass);
    }
    #[test] fn invalid_duplicate_ai_evidence_fails() {
        let mut f = facts(THREE_DAYS + 10);
        f.ai_reviews.push(f.ai_reviews[0].clone());
        assert!(!evaluate(&f).pass);
    }
    #[test] fn same_ai_event_id_across_providers_is_not_two_reviews() {
        let mut f = facts(10);
        f.ai_reviews[1].review_id = f.ai_reviews[0].review_id;
        assert!(!evaluate(&f).pass);
    }
    #[test] fn older_ai_success_cannot_hide_latest_unverified_evidence() {
        let mut f = facts(THREE_DAYS + 10); f.human_reviews.clear(); f.ai_reviews.pop();
        f.ai_reviews.push(AiReview {review_id: 89, published_at: T + 8,
            provider: AiProvider::OpenAi, head_sha: SHA.into(),
            succeeded: true, verified_source: false });
        assert!(!evaluate(&f).pass);
    }
    #[test] fn draft_opened_long_ago_gets_new_strict_cycle_on_ready() {
        let mut f = facts(TEN_DAYS + 45);
        f.created_as_draft = true;
        f.readiness_events = vec![ReadinessEvent { event_id: 1, at: T + TEN_DAYS,
            state: ReadinessState::Ready }];
        assert_eq!(ready_cycle_start(&f), Ok(Some(T + TEN_DAYS)));
        assert_eq!(evaluate(&f).window, ReviewWindow::StrictInitial);
        assert!(!evaluate(&f).pass); // Old creation-era reviews are not current-cycle approvals.
    }
    #[test] fn ready_to_draft_to_ready_restarts_clock() {
        let mut f = facts(TEN_DAYS + THREE_DAYS - 1);
        f.readiness_events = vec![
            ReadinessEvent { event_id: 1, at: T + 10, state: ReadinessState::Draft },
            ReadinessEvent { event_id: 2, at: T + TEN_DAYS, state: ReadinessState::Ready },
        ];
        assert_eq!(evaluate(&f).window, ReviewWindow::StrictInitial);
        assert!(!evaluate(&f).pass);
        f.now = T + TEN_DAYS + THREE_DAYS;
        f.human_reviews = vec![human(333, T + TEN_DAYS + 2)];
        f.ai_reviews.clear();
        f.overlap_audit.as_mut().unwrap().completed_at = T + TEN_DAYS;
        assert_eq!(evaluate(&f).window, ReviewWindow::Accelerated);
        assert!(evaluate(&f).pass);
    }
    #[test] fn repeated_draft_cycle_cannot_reuse_old_fast_lane_approval() {
        let mut f = facts(TEN_DAYS + THREE_DAYS);
        f.readiness_events = vec![
            ReadinessEvent { event_id: 1, at: T + 10, state: ReadinessState::Draft },
            ReadinessEvent { event_id: 2, at: T + TEN_DAYS, state: ReadinessState::Ready },
        ];
        f.overlap_audit.as_mut().unwrap().completed_at = T + TEN_DAYS;
        f.human_reviews = vec![human(333, T + 20)];
        f.ai_reviews.clear();
        assert!(!evaluate(&f).pass);
    }
    #[test] fn draft_transition_blocks_merge_and_can_reset_after_new_ready() {
        let mut f = facts(THREE_DAYS + 10);
        f.readiness_events.push(ReadinessEvent { event_id: 1, at: T + 20,
            state: ReadinessState::Draft });
        f.draft = true;
        assert_eq!(evaluate(&f).window, ReviewWindow::Draft);
        assert!(!evaluate(&f).pass);
    }
    #[test] fn unknown_or_contradictory_lifecycle_fails_closed() {
        let mut f = facts(THREE_DAYS + 10);
        f.lifecycle_complete = false;
        assert!(!evaluate(&f).pass);
        f.lifecycle_complete = true;
        f.created_as_draft = true;
        assert!(!evaluate(&f).pass);
        f.created_as_draft = false;
        f.readiness_events.push(ReadinessEvent { event_id: 1, at: T + 4,
            state: ReadinessState::Ready });
        assert!(!evaluate(&f).pass);
    }
    #[test] fn transition_reordering_duplicate_and_future_events_rejected() {
        let mut f = facts(TEN_DAYS + 10);
        f.readiness_events = vec![
            ReadinessEvent { event_id: 2, at: T + TEN_DAYS, state: ReadinessState::Draft },
            ReadinessEvent { event_id: 1, at: T + TEN_DAYS - 1, state: ReadinessState::Ready },
        ];
        assert!(!evaluate(&f).pass);
        f.readiness_events[1] = ReadinessEvent { event_id: 2, at: T + TEN_DAYS + 1,
            state: ReadinessState::Ready };
        assert!(!evaluate(&f).pass);
        f.readiness_events[1].event_id = 3;
        f.readiness_events[1].at = f.now + 1;
        assert!(!evaluate(&f).pass);
    }
    #[test] fn keep_draft_and_not_ready_block_automated_merge() {
        let mut f = facts(THREE_DAYS + 10);
        f.labels.push("keep-draft".into());
        assert!(!evaluate(&f).pass);
        f.labels = vec!["NOT-READY".into()];
        assert!(!evaluate(&f).pass);
        f.labels.clear(); f.labels_verified = false;
        assert!(!evaluate(&f).pass);
    }
    #[test] fn missing_stale_or_unverified_overlap_blocks_fast_lane() {
        let mut f = facts(THREE_DAYS + 10);
        f.overlap_audit = None;
        assert!(!evaluate(&f).pass);
        f.overlap_audit = facts(10).overlap_audit;
        f.overlap_audit.as_mut().unwrap().verified_source = false;
        assert!(!evaluate(&f).pass);
        f.overlap_audit.as_mut().unwrap().verified_source = true;
        f.open_pr_index_version = 2;
        assert!(!evaluate(&f).pass);
        f.open_pr_index_version = 1;
        f.head_sha = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb".into();
        f.ci_runs[0].head_sha = f.head_sha.clone();
        assert!(!evaluate(&f).pass);
    }
    #[test] fn unresolved_overlap_blocks_until_competing_pr_is_integrated() {
        let mut f = facts(THREE_DAYS + 10);
        let a = f.overlap_audit.as_mut().unwrap();
        a.candidates.push(OverlapCandidate { repository: "atto-lang/atto-source.rs".into(),
            pr_number: 123, disposition: OverlapDisposition::Unresolved,
            rationale: "Conflicting parser feature".into() });
        assert!(!evaluate(&f).pass);
        f.overlap_audit.as_mut().unwrap().candidates[0].disposition =
            OverlapDisposition::Incorporated;
        assert!(evaluate(&f).pass);
    }
    #[test] fn duplicate_overlap_candidate_and_empty_rationale_fail() {
        let mut f = facts(THREE_DAYS + 10);
        let c = OverlapCandidate { repository: "org/repo".into(), pr_number: 7,
            disposition: OverlapDisposition::Independent, rationale: String::new() };
        f.overlap_audit.as_mut().unwrap().candidates.push(c.clone());
        assert!(!evaluate(&f).pass);
        f.overlap_audit.as_mut().unwrap().candidates[0].rationale = "Different API".into();
        f.overlap_audit.as_mut().unwrap().candidates.push(c);
        assert!(!evaluate(&f).pass);
    }
    #[test] fn draft_promotion_hold_labels_and_preflight() {
        let mut f = facts(10);
        f.created_as_draft = true;
        f.draft = true;
        assert!(evaluate_draft_promotion(&f).0);
        assert!(!evaluate(&f).pass);
        f.labels.push("keep-draft".into());
        assert!(!evaluate_draft_promotion(&f).0);
        f.labels = vec!["not-ready".into()];
        assert!(!evaluate_draft_promotion(&f).0);
        f.labels.clear();
        f.draft_work_complete = false;
        assert!(!evaluate_draft_promotion(&f).0);
        f.draft_work_complete = true;
        f.overlap_audit = None;
        assert!(!evaluate_draft_promotion(&f).0);
    }
    #[test] fn draft_promotion_recovers_after_overlap_resolution() {
        let mut f = facts(10);
        f.created_as_draft = true;
        f.draft = true;
        f.overlap_audit.as_mut().unwrap().candidates.push(
            OverlapCandidate { repository: "org/competing".into(), pr_number: 2,
                disposition: OverlapDisposition::Unresolved,
                rationale: "Competes with this draft".into() });
        assert!(!evaluate_draft_promotion(&f).0);
        f.overlap_audit.as_mut().unwrap().candidates[0].disposition =
            OverlapDisposition::Updated;
        assert!(evaluate_draft_promotion(&f).0);
    }

}
