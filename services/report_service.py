"""
Report Service for generating AI-powered commentary from news data.

This service takes structured news data (from the topic search service)
and generates:
1. Executive briefs (one bullet point per topic)
2. Wall Street-style desk note (cohesive narrative)

Using Google's Gemini AI with structured output.
"""

import asyncio
import os
import yaml
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime
import logging

from pydantic import BaseModel

from .gemini_service import GeminiService

logger = logging.getLogger(__name__)


class TopicBrief(BaseModel):
    """A single topic brief for a company."""
    company_name: str
    topic_name: str
    bullet_point: str


class DeskNote(BaseModel):
    """Wall Street-style desk note report."""
    report: str


class Commentary(BaseModel):
    """Complete commentary with briefs and desk note."""
    ticker: str
    company_name: str
    generated_at: str
    briefs: List[TopicBrief]
    desk_note: str


class ReportService:
    """
    Service for generating AI-powered commentary from news data.
    
    This service takes the output from the topic search service
    and generates executive briefs and Wall Street desk notes.
    """
    
    def __init__(
        self,
        gemini_service: Optional[GeminiService] = None,
        prompts_path: str = "config/prompts.yaml"
    ):
        """
        Initialize the report service.
        
        Args:
            gemini_service: Optional GeminiService instance. If not provided,
                          will create one using environment variables.
            prompts_path: Path to prompts.yaml file
        """
        self.gemini_service = gemini_service or self._create_gemini_service()
        self.prompts_path = prompts_path
        self.prompts = self._load_prompts()
    
    def _create_gemini_service(self) -> GeminiService:
        """Create a GeminiService from environment (see ``GeminiService`` for resolution order)."""
        logger.info("Creating GeminiService from environment variables")
        return GeminiService(model="gemini-2.5-flash")
    
    def _load_prompts(self) -> Dict[str, Any]:
        """Load prompt templates from YAML file."""
        try:
            with open(self.prompts_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            logger.error(f"Prompts file not found: {self.prompts_path}")
            raise
    
    def _format_context_from_news_response(self, news_response: Dict[str, Any]) -> str:
        """
        Format context from news API response for Gemini processing.
        
        Args:
            news_response: Response from /api/news endpoint with topic_results
            
        Returns:
            Formatted context string
        """
        company_name = news_response.get('company_name', 'Unknown Company')
        topic_results = news_response.get('topic_results', [])
        
        # Group articles by topic
        topics_dict = {}
        for article in topic_results:
            topic = article.get('topic', 'Unknown Topic')
            if topic not in topics_dict:
                topics_dict[topic] = []
            topics_dict[topic].append(article)
        
        # Format context for each topic
        all_contexts = []
        for topic, articles in topics_dict.items():
            context_parts = [
                "<company_name>",
                f"{company_name}",
                "<topic>",
                f"{topic}",
                "<query>",
                f"{topic}",  # Use topic as the query
            ]
            
            # Add all article full_text as answer chunks
            for article in articles:
                full_text = article.get('full_text', '')
                document_url = article.get('document_url', '')
                if full_text:
                    context_parts.append("<answer_chunk>")
                    if document_url:
                        context_parts.append(f"<source_url>{document_url}</source_url>")
                    context_parts.append(full_text)
                    context_parts.append("</answer_chunk>")
            
            all_contexts.append("\n".join(context_parts))
        
        return "\n\n".join(all_contexts)
    
    def _render_prompt(
        self,
        template: str,
        **variables
    ) -> str:
        """
        Render a prompt template with variables.
        
        Args:
            template: Template string with {{variable}} placeholders
            **variables: Variables to substitute
            
        Returns:
            Rendered prompt string
        """
        rendered = template
        for key, value in variables.items():
            placeholder = f"{{{{{key}}}}}"  # {{key}}
            rendered = rendered.replace(placeholder, str(value))
        return rendered
    
    async def generate_topic_briefs(
        self,
        news_response: Dict[str, Any]
    ) -> List[TopicBrief]:
        """
        Generate executive briefs (one per topic) from news data.
        
        Args:
            news_response: Response from /api/news endpoint
            
        Returns:
            List of TopicBrief objects
        """
        logger.info(f"Generating topic briefs for {news_response.get('ticker', 'unknown')}")
        
        # Format context
        context = self._format_context_from_news_response(news_response)
        
        # Load prompt template
        prompt_config = self.prompts['executive_brief']
        system_prompt = prompt_config['system_prompt']
        user_template = prompt_config['user_template']
        
        # Render prompt
        current_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
        user_prompt = self._render_prompt(
            user_template,
            current_datetime=current_datetime,
            report=context,
            response_format="See above for expected JSON schema"
        )
        
        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        
        # Generate briefs
        briefs = await self.gemini_service.generate_content_list(
            prompt=full_prompt,
            response_schema=TopicBrief
        )
        
        logger.info(f"Generated {len(briefs)} topic briefs")
        return briefs
    
    async def generate_desk_note(
        self,
        briefs: List[TopicBrief]
    ) -> str:
        """
        Generate Wall Street-style desk note from topic briefs.
        
        Args:
            briefs: List of TopicBrief objects
            
        Returns:
            Desk note text
        """
        logger.info(f"Generating desk note from {len(briefs)} briefs")
        
        # Format briefs for prompt
        briefs_text = "\n\n".join([
            f"Topic: {brief.topic_name}\n"
            f"Company: {brief.company_name}\n"
            f"Brief: {brief.bullet_point}"
            for brief in briefs
        ])
        
        # Load prompt template
        prompt_config = self.prompts['wallstreet_desk_note']
        system_prompt = prompt_config['system_prompt']
        user_template = prompt_config['user_template']
        
        # Render prompt
        current_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
        user_prompt = self._render_prompt(
            user_template,
            current_datetime=current_datetime,
            briefs=briefs_text
        )
        
        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        
        # Generate desk note
        result = await self.gemini_service.generate_content(
            prompt=full_prompt,
            response_schema=DeskNote
        )
        
        logger.info("Desk note generated successfully")
        return result.report
    
    async def generate_commentary(
        self,
        news_response: Dict[str, Any]
    ) -> Commentary:
        """
        Generate complete commentary (briefs + desk note) from news data.
        
        This is the main method to call from the API endpoint.
        
        Args:
            news_response: Response from /api/news endpoint containing:
                - ticker: Stock ticker
                - company_name: Company name
                - topic_results: List of articles grouped by topic
            
        Returns:
            Commentary object with briefs and desk_note
        """
        ticker = news_response.get('ticker', 'UNKNOWN')
        company_name = news_response.get('company_name', 'Unknown Company')
        
        logger.info(f"Generating commentary for {ticker} ({company_name})")
        
        # Generate topic briefs
        briefs = await self.generate_topic_briefs(news_response)
        
        # Generate desk note from briefs
        desk_note = await self.generate_desk_note(briefs)
        
        # Create commentary object
        commentary = Commentary(
            ticker=ticker,
            company_name=company_name,
            generated_at=datetime.now().isoformat(),
            briefs=briefs,
            desk_note=desk_note
        )
        
        logger.info(f"Commentary generated successfully for {ticker}")
        return commentary


# Convenience function for one-off commentary generation
async def generate_commentary_from_news(
    news_response: Dict[str, Any],
    gemini_service: Optional[GeminiService] = None
) -> Commentary:
    """
    Convenience function to generate commentary without instantiating a service.
    
    Args:
        news_response: Response from /api/news endpoint
        gemini_service: Optional GeminiService instance
        
    Returns:
        Commentary object
    """
    service = ReportService(gemini_service=gemini_service)
    return await service.generate_commentary(news_response)

