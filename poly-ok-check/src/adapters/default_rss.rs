use std::collections::HashMap;

use async_trait::async_trait;
use chrono::Utc;
use feed_rs::parser;
use reqwest::Client;

use crate::config::MarketNewsRule;
use crate::contracts::NewsEvent;
use crate::data_hub::{DataHubError, NewsProvider};

pub struct RssNewsProvider {
    client: Client,
    feeds: HashMap<String, String>,
    market_rules: HashMap<String, MarketNewsRule>,
}

impl RssNewsProvider {
    pub fn new(feeds: HashMap<String, String>, market_rules: Vec<MarketNewsRule>) -> Self {
        let rule_map = market_rules
            .into_iter()
            .map(|rule| (rule.market_id.clone(), rule))
            .collect();
        Self {
            client: Client::new(),
            feeds,
            market_rules: rule_map,
        }
    }

    fn feed_sources_for_market(&self, market_id: &str) -> Vec<(String, String)> {
        if let Some(rule) = self.market_rules.get(market_id) {
            if !rule.feed_sources.is_empty() {
                return rule
                    .feed_sources
                    .iter()
                    .filter_map(|source| {
                        self.feeds
                            .get(source)
                            .map(|url| (source.clone(), url.clone()))
                    })
                    .collect();
            }
        }
        self.feeds
            .iter()
            .map(|(source, url)| (source.clone(), url.clone()))
            .collect()
    }

    fn keywords_for_market(&self, market_id: &str) -> Vec<String> {
        if let Some(rule) = self.market_rules.get(market_id) {
            if !rule.keywords.is_empty() {
                return rule
                    .keywords
                    .iter()
                    .map(|keyword| keyword.to_ascii_lowercase())
                    .collect();
            }
        }
        vec![market_id.to_ascii_lowercase()]
    }
}

#[async_trait]
impl NewsProvider for RssNewsProvider {
    async fn fetch_news(
        &self,
        market_id: &str,
        since: chrono::DateTime<Utc>,
        limit: usize,
    ) -> Result<Vec<NewsEvent>, DataHubError> {
        let keywords = self.keywords_for_market(market_id);
        let mut out = Vec::new();

        for (source, url) in self.feed_sources_for_market(market_id) {
            let bytes = self
                .client
                .get(&url)
                .send()
                .await
                .map_err(|e| DataHubError::Provider(format!("rss request failed for {url}: {e}")))?
                .bytes()
                .await
                .map_err(|e| DataHubError::Provider(format!("rss bytes failed for {url}: {e}")))?;

            let feed = parser::parse(&bytes[..])
                .map_err(|e| DataHubError::Provider(format!("rss parse failed for {url}: {e}")))?;

            for entry in feed.entries {
                let headline = entry
                    .title
                    .as_ref()
                    .map(|x| x.content.clone())
                    .unwrap_or_default();
                let summary = entry
                    .summary
                    .as_ref()
                    .map(|x| x.content.clone())
                    .unwrap_or_default();
                let haystack = format!("{} {}", headline, summary).to_ascii_lowercase();
                if !keywords.iter().any(|keyword| haystack.contains(keyword)) {
                    continue;
                }

                let published = entry
                    .published
                    .map(|x| x.with_timezone(&Utc))
                    .unwrap_or_else(Utc::now);
                if published < since {
                    continue;
                }

                let link = entry.links.first().map(|l| l.href.clone());
                out.push(NewsEvent {
                    event_id: format!("{source}-{}", entry.id),
                    market_id: market_id.to_string(),
                    headline,
                    source: source.clone(),
                    url: link,
                    published_at: published,
                    tags: vec!["rss".to_string()],
                });
            }
        }

        out.sort_by_key(|x| x.published_at);
        out.reverse();
        out.truncate(limit);
        Ok(out)
    }
}
