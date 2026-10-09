import type { CoachStep } from './CoachMarks';

export const APPLICATION_TOUR_KEY = 'qp_tour_application_v2';
export const AGENT_TOUR_KEY = 'qp_tour_agent_v2';
export const ARCHITECTURE_TOUR_KEY = 'qp_tour_architecture_v2';

export const APPLICATION_TOUR: CoachStep[] = [
  {
    title: 'Welcome to QP1',
    body: 'A quick tour of the quant trading platform. You can skip anytime.',
    placement: 'auto',
  },
  {
    selector: '[data-tour="navigation"]',
    title: 'Navigate the platform',
    body: 'Switch between Market Explorer, Options Analytics, SEC Research, AI Agent, and more. On mobile, open this with the menu button.',
  },
  {
    selector: '[data-tour="market-research"]',
    title: 'Market research',
    body: 'Explore OHLCV data and options analytics for any symbol. Charts and metrics update in real time.',
    navigateTo: 'market',
    waitForTargetTimeout: 3000,
  },
  {
    selector: '[data-tour="agent"]',
    title: 'AI Research Agent',
    body: 'Ask natural-language questions about market data, signals, and SEC filings. The agent retrieves, grounds, and verifies each answer.',
    navigateTo: 'agent',
    waitForTargetTimeout: 3000,
  },
  {
    selector: '[data-tour="analytics-evidence"]',
    title: 'Analytics & evidence',
    body: 'Monitor model performance, latency, and agent activity. Every metric is traceable to its source.',
    navigateTo: 'health',
    waitForTargetTimeout: 3000,
  },
];

export const AGENT_TOUR: CoachStep[] = [
  {
    title: 'Research Agent tour',
    body: 'A 4-step walkthrough of the AI research agent. Skip anytime.',
    placement: 'auto',
  },
  {
    selector: '[data-tour="agent"]',
    title: 'Open the agent',
    body: 'The Research Agent answers questions about market data, signals, and SEC filings using retrieval-augmented generation.',
    navigateTo: 'agent',
    waitForTargetTimeout: 3000,
  },
  {
    selector: '[data-tour="agent-input"]',
    title: 'Ask a question',
    body: 'Type a research question or select a suggested prompt. The agent will retrieve relevant information from SEC filings and market data.',
  },
  {
    selector: '[data-tour="agent-evidence"]',
    title: 'Evidence trail',
    body: 'Every agent response includes tool calls and sources. Inspect the evidence instead of trusting a black box.',
  },
];

export const ARCHITECTURE_TOUR: CoachStep[] = [
  {
    title: 'Architecture & pipeline tour',
    body: 'A 4-step look at the platform architecture. Skip anytime.',
    placement: 'auto',
  },
  {
    selector: '[data-tour="navigation"]',
    title: 'Navigate to Architecture',
    body: 'Find the Architecture & Tests screen under the Evidence section in the sidebar.',
  },
  {
    selector: '[data-tour="provenance"]',
    title: 'Provenance & lineage',
    body: 'Track data from source through transformation to consumption. Every table and metric has a verified lineage.',
    navigateTo: 'architecture',
    waitForTargetTimeout: 3000,
  },
  {
    selector: '[data-tour="pipeline-nodes"]',
    title: 'Pipeline nodes',
    body: 'The architecture diagram shows ingestion, feature engineering, signal generation, and execution stages. Each node links to its test evidence.',
  },
];