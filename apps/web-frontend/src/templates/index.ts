/**
 * Template registry - exports all available workflow templates
 */
import { FlowTemplate } from '../types';
import { blogPostWriterTemplate } from './BlogPostWriter';
import { illustratedStoryTemplate } from './IllustratedStory';
import { chatbotWithMemoryTemplate } from './ChatbotWithMemory';
import { twoBrainInboxTemplate } from './TwoBrainInbox';
import { contentEngineTemplate } from './ContentEngine';
import { apiFetchTemplate } from './ApiFetch';
import { faultlineComplianceTemplate } from './FaultlineCompliance';
import { socialMediaMonitorTemplate } from './SocialMediaMonitor';
import { documentProcessorTemplate } from './DocumentProcessor';
import { dataPipelineTemplate } from './DataPipeline';

// Export all templates
export const templates: FlowTemplate[] = [
  blogPostWriterTemplate,
  illustratedStoryTemplate,
  chatbotWithMemoryTemplate,
  twoBrainInboxTemplate,
  contentEngineTemplate,
  apiFetchTemplate,
  faultlineComplianceTemplate,
  socialMediaMonitorTemplate,
  documentProcessorTemplate,
  dataPipelineTemplate,
];

// Helper function to get a template by ID
export const getTemplateById = (id: string): FlowTemplate | undefined => {
  return templates.find(template => template.id === id);
};

// Export default
export default templates;
