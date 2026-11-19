//! Standalone, fail-closed PR policy decision logic.
//! Input MUST come from a trusted GitHub App, never from PR-controlled JSON.
use std::collections::BTreeMap;

pub const ORESOFTWARE: u64 = 11_139_560;
pub const THE1MILLS: u64 = 2_148_448;
pub const THREE_DAYS: u64 = 72 * 60 * 60;

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
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum AiProvider { OpenAi, Anthropic }
#[derive(Clone, Debug)]
pub struct AiReview {
    pub provider: AiProvider,
    pub head_sha: String,
    pub succeeded: bool,
    /// Asserted only by a trusted integration after verifying the source App.
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
#[derive(Clone, Debug)]
pub struct OverrideEvent {
    pub pr_number: u64,
    pub head_sha: String,
    pub actor_id: u64,
    pub at: u64,
    pub has_write_access: bool,
    /// True only for an App-authenticated, append-only audit event.
    pub verified_event: bool,
}
#[derive(Clone, Debug)]
pub struct Facts {
    pub pr_number: u64,
    pub created_at: u64,
    pub now: u64,
    pub author_id: u64,
    pub head_sha: String,
    pub draft: bool,
    pub human_reviews: Vec<HumanReview>,
    pub ai_reviews: Vec<AiReview>,
    pub required_ci: Vec<RequiredCi>,
    pub ci_runs: Vec<CiRun>,
    pub override_event: Option<OverrideEvent>,
}
#[derive(Debug)]
pub struct Decision {
    pub pass: bool,
    pub eligible_for_override: bool,
    pub override_applied: bool,
    pub blockers: Vec<String>,
}
fn named_human(id: u64) -> bool { id == ORESOFTWARE || id == THE1MILLS }

pub fn evaluate(f: &Facts) -> Decision {
    let mut blockers = Vec::<String>::new();
    if f.pr_number == 0 || f.head_sha.is_empty() {
        blockers.push("invalid PR identity".into());
    }
    if f.draft { blockers.push("draft PR".into()); }
    if f.now < f.created_at { blockers.push("future PR creation timestamp".into()); }

    // The equality boundary at exactly 72 hours is still strict.
    let eligible = f.now.saturating_sub(f.created_at) > THREE_DAYS;
    let overridden = eligible && f.override_event.as_ref().is_some_and(|o| {
        o.verified_event && o.pr_number == f.pr_number && o.head_sha == f.head_sha
            && named_human(o.actor_id) && o.actor_id != f.author_id
            && o.has_write_access
            && o.at > f.created_at.saturating_add(THREE_DAYS) && o.at <= f.now
    });

    // CI is always required, even for old PRs and even after an override.
    if f.required_ci.is_empty() {
        blockers.push("no required CI configured".into());
    }
    let mut required_names = std::collections::BTreeSet::new();
    for required in &f.required_ci {
        if required.name.trim().is_empty() || required.app_id == 0
            || required.name == "review-policy"
            || !required_names.insert((&required.name, required.app_id))
        {
            blockers.push(format!("invalid required CI configuration: {}", required.name));
            continue;
        }
        let found: Vec<_> = f.ci_runs.iter().filter(|r| {
            r.name == required.name && r.app_id == required.app_id && r.head_sha == f.head_sha
        }).collect();
        if found.len() != 1 {
            blockers.push(format!("missing or ambiguous required CI: {}", required.name));
        } else if found[0].state != CiState::Success {
            blockers.push(format!("required CI not successful: {}", required.name));
        }
    }

    // GitHub review chronology: the latest state supersedes an earlier state.
    let mut latest: BTreeMap<u64, &HumanReview> = BTreeMap::new();
    for r in &f.human_reviews {
        if r.submitted_at > f.now {
            blockers.push("future-dated review".into());
            continue;
        }
        let replace = latest.get(&r.actor_id)
            .map_or(true, |prev| (r.submitted_at, r.review_id) > (prev.submitted_at, prev.review_id));
        if replace { latest.insert(r.actor_id, r); }
    }
    if latest.values().any(|r| r.has_write_access && r.state == ReviewState::ChangesRequested) {
        blockers.push("unresolved changes requested".into());
    }
    let approval = |id| latest.get(&id).is_some_and(|r| {
        id != f.author_id && r.has_write_access && r.head_sha == f.head_sha
            && r.state == ReviewState::Approved
    });

    if overridden {
        if !approval(ORESOFTWARE) && !approval(THE1MILLS) {
            blockers.push("aged override requires one designated independent human approval".into());
        }
    } else {
        for id in [ORESOFTWARE, THE1MILLS] {
            if !approval(id) {
                blockers.push(format!("missing current approval from {}", id));
            }
        }
        for provider in [AiProvider::OpenAi, AiProvider::Anthropic] {
            if !f.ai_reviews.iter().any(|a| {
                a.provider == provider && a.head_sha == f.head_sha
                    && a.succeeded && a.verified_source
            }) {
                blockers.push(format!("missing verified {:?} AI review", provider));
            }
        }
    }

    Decision { pass: blockers.is_empty(), eligible_for_override: eligible,
        override_applied: overridden, blockers }
}

#[cfg(test)]
mod tests {
    use super::*;
    const T: u64 = 1_000_000;
    fn approve(actor_id: u64) -> HumanReview {
        HumanReview { actor_id, review_id: actor_id, submitted_at: T+1,
            head_sha: "abc".into(), state: ReviewState::Approved, has_write_access: true }
    }
    fn facts(age: u64) -> Facts {
        Facts { pr_number: 42, created_at: T, now: T+age,
            author_id: 999, head_sha: "abc".into(), draft: false,
            human_reviews: vec![approve(ORESOFTWARE), approve(THE1MILLS)],
            ai_reviews: vec![
                AiReview { provider: AiProvider::OpenAi, head_sha: "abc".into(),
                    succeeded: true, verified_source: true },
                AiReview { provider: AiProvider::Anthropic, head_sha: "abc".into(),
                    succeeded: true, verified_source: true }
            ],
            required_ci: vec![RequiredCi {name: "build".into(), app_id: 101}],
            ci_runs: vec![CiRun {name: "build".into(), app_id: 101,
                head_sha: "abc".into(), state: CiState::Success}],
            override_event: None }
    }
    fn authorize(f: &mut Facts) {
        f.override_event = Some(OverrideEvent {
            pr_number: 42, head_sha: "abc".into(), actor_id: ORESOFTWARE,
            at: T + THREE_DAYS + 1, has_write_access: true, verified_event: true });
    }
    #[test] fn strict_passes() { assert!(evaluate(&facts(THREE_DAYS)).pass); }
    #[test] fn missing_human_blocks() {
        let mut f = facts(40); f.human_reviews.pop(); assert!(!evaluate(&f).pass);
    }
    #[test] fn missing_ai_blocks() {
        let mut f = facts(40); f.ai_reviews.pop(); assert!(!evaluate(&f).pass);
    }
    #[test] fn boundary_is_strict() {
        let mut f = facts(THREE_DAYS); authorize(&mut f);
        f.human_reviews.pop(); f.ai_reviews.clear();
        assert!(!evaluate(&f).pass);
    }
    #[test] fn age_alone_is_not_a_bypass() {
        let mut f = facts(THREE_DAYS+10);
        f.human_reviews.pop(); f.ai_reviews.clear();
        assert!(!evaluate(&f).pass);
    }
    #[test] fn explicit_old_override_one_human_passes() {
        let mut f = facts(THREE_DAYS+1); authorize(&mut f);
        f.human_reviews.pop(); f.ai_reviews.clear();
        let d = evaluate(&f); assert!(d.pass, "{:?}", d.blockers);
        assert!(d.override_applied);
    }
    #[test] fn unsigned_and_unauthorized_override_blocks() {
        let mut f = facts(THREE_DAYS+10); authorize(&mut f);
        f.human_reviews.pop(); f.ai_reviews.clear();
        f.override_event.as_mut().unwrap().verified_event = false;
        assert!(!evaluate(&f).pass);
        f.override_event.as_mut().unwrap().verified_event = true;
        f.override_event.as_mut().unwrap().actor_id = 123;
        assert!(!evaluate(&f).pass);
    }
    #[test] fn replayed_override_different_head_or_pr_blocks() {
        let mut f = facts(THREE_DAYS+10); authorize(&mut f);
        f.human_reviews.pop(); f.ai_reviews.clear();
        f.override_event.as_mut().unwrap().head_sha = "wrong".into();
        assert!(!evaluate(&f).pass);
        f.override_event.as_mut().unwrap().head_sha = "abc".into();
        f.override_event.as_mut().unwrap().pr_number = 43;
        assert!(!evaluate(&f).pass);
    }
    #[test] fn author_cannot_approve_self() {
        let mut f = facts(20); f.author_id = ORESOFTWARE;
        assert!(!evaluate(&f).pass);
    }
    #[test] fn latest_changes_requested_blocks_until_new_approval() {
        let mut f = facts(20);
        f.human_reviews.push(HumanReview {
            actor_id: THE1MILLS, review_id: 900, submitted_at: T+2,
            head_sha: "abc".into(), state: ReviewState::ChangesRequested,
            has_write_access: true });
        assert!(!evaluate(&f).pass);
        f.human_reviews.push(HumanReview {
            actor_id: THE1MILLS, review_id: 901, submitted_at: T+3,
            head_sha: "abc".into(), state: ReviewState::Approved,
            has_write_access: true });
        assert!(evaluate(&f).pass);
    }
    #[test] fn stale_or_dismissed_human_review_blocks() {
        let mut f = facts(20);
        f.human_reviews[0].head_sha = "old".into(); assert!(!evaluate(&f).pass);
        f.human_reviews[0].head_sha = "abc".into();
        f.human_reviews[0].state = ReviewState::Dismissed;
        assert!(!evaluate(&f).pass);
    }
    #[test] fn unverified_or_stale_ai_blocks() {
        let mut f = facts(20);
        f.ai_reviews[0].verified_source = false; assert!(!evaluate(&f).pass);
        f.ai_reviews[0].verified_source = true;
        f.ai_reviews[0].head_sha = "old".into(); assert!(!evaluate(&f).pass);
    }
    #[test] fn failed_pending_skipped_neutral_ci_block_even_aged() {
        let mut f = facts(THREE_DAYS+10); authorize(&mut f);
        f.human_reviews.pop(); f.ai_reviews.clear();
        for state in [CiState::Failure, CiState::Pending, CiState::Skipped, CiState::Neutral] {
            f.ci_runs[0].state = state;
            assert!(!evaluate(&f).pass);
        }
    }
    #[test] fn missing_duplicate_wrong_app_or_stale_ci_blocks() {
        let mut f = facts(20);
        f.ci_runs.clear(); assert!(!evaluate(&f).pass);
        f.ci_runs.push(CiRun {name:"build".into(),app_id:101,
            head_sha:"abc".into(),state:CiState::Success});
        f.ci_runs.push(f.ci_runs[0].clone());
        assert!(!evaluate(&f).pass);
        f.ci_runs.pop(); f.ci_runs[0].app_id=102;
        assert!(!evaluate(&f).pass);
        f.ci_runs[0].app_id=101; f.ci_runs[0].head_sha="old".into();
        assert!(!evaluate(&f).pass);
    }
    #[test] fn missing_ci_config_and_circular_check_block() {
        let mut f = facts(20);
        f.required_ci.clear(); assert!(!evaluate(&f).pass);
        f.required_ci.push(RequiredCi{name:"review-policy".into(),app_id:101});
        assert!(!evaluate(&f).pass);
    }
    #[test] fn draft_or_future_pr_blocks() {
        let mut f = facts(20); f.draft=true; assert!(!evaluate(&f).pass);
        f.draft=false; f.now=T-1; assert!(!evaluate(&f).pass);
    }
    #[test] fn author_cannot_grant_override() {
        let mut f = facts(THREE_DAYS+1); authorize(&mut f);
        f.author_id = ORESOFTWARE;
        f.human_reviews.retain(|r|r.actor_id==THE1MILLS);
        f.ai_reviews.clear();
        assert!(!evaluate(&f).pass);
    }
}
