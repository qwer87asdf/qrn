#!/usr/bin/env python3
"""
Quran HTML Parser
Parses HTML pages from Tarteel Quran layout and maps word data to create line mappings
"""

import json
import re
from typing import Dict, List, Optional, Tuple
import requests
from bs4 import BeautifulSoup
from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class LineMapping:
    """Data class for line mapping information"""
    page_number: int
    line_number: int
    line_type: str  # "surah_name", "bismillah", or "ayah"
    first_word_number: Optional[int]
    last_word_number: Optional[int]
    chapter_number: Optional[int]
    verse_number: Optional[int] = None  # Added for tracking verses


@dataclass
class ValidationIssue:
    """Data class for tracking validation issues"""
    page_number: int
    line_number: int
    issue_type: str
    description: str
    data_location: Optional[str] = None
    suggested_fix: Optional[str] = None
    html_context: Optional[str] = None


class QuranParser:
    def __init__(self, base_url: str = "https://qul.tarteel.ai/resources/mushaf-layout/12"):
        self.base_url = base_url
        self.word_data = []  # For backward compatibility if needed
        self.line_mappings = []
        self.validation_issues = []  # Track validation issues
        
        # Chapter-based optimization
        self.chapter_data = {}  # chapter_number -> word_list
        self.chapter_caches = {}  # chapter_number -> verse:position cache
        self.loaded_chapters = set()  # Track which chapters are loaded
        self.word_data_dir = None  # Directory containing chapter JSON files
        
        # Global position tracking (for sequential access across chapters)
        self.last_chapter = None
        self.last_position_in_chapter = 0
        self.global_word_counter = 0  # Track global position for backward compatibility
        
        # Performance statistics
        self.cache_hits = 0
        self.chapter_file_loads = 0
        self.sequential_hits = 0
        self.total_lookups = 0
        self.fallback_matches = 0  # Track fallback matching success
        
    def load_word_data_directory(self, data_directory: str):
        """Load word data from directory containing chapter-based JSON files (1.json, 2.json, etc.)"""
        import os
        
        self.word_data_dir = data_directory
        
        # Count available chapter files
        chapter_files = []
        for i in range(1, 115):  # Chapters 1-114
            chapter_file = os.path.join(data_directory, f"{i}_en.json")
            if os.path.exists(chapter_file):
                chapter_files.append(i)
        
        print(f"Found {len(chapter_files)} chapter files in {data_directory}")
        print("Chapter-based loading enabled - chapters will be loaded on demand")
        
        # Pre-load first few chapters for immediate use
        self._preload_chapters([1, 2, 3, 4, 5])
        
    def load_word_data(self, json_file_path: str):
        """Load word data from single JSON file (legacy support)"""
        import os
        
        # Check if it's a directory path instead of file
        if os.path.isdir(json_file_path):
            self.load_word_data_directory(json_file_path)
            return
            
        # Legacy single file loading
        with open(json_file_path, 'r', encoding='utf-8') as f:
            self.word_data = json.load(f)
        
        print(f"Loaded {len(self.word_data)} words from single JSON file")
        print("Building optimization indices...")
        
        # Build lookup cache and chapter indices for single file
        self._build_lookup_indices()
        print(f"Built indices for {len(self.chapter_start_indices)} chapters")
    
    def _preload_chapters(self, chapter_numbers: List[int]):
        """Pre-load specific chapters for immediate use"""
        for chapter_num in chapter_numbers:
            self._load_chapter(chapter_num)
            
    def _load_chapter(self, chapter_number: int) -> bool:
        """Load a specific chapter's data on demand"""
        if chapter_number in self.loaded_chapters:
            return True
            
        if not self.word_data_dir:
            return False
            
        import os
        chapter_file = os.path.join(self.word_data_dir, f"{chapter_number}_en.json")
        
        if not os.path.exists(chapter_file):
            print(f"Warning: Chapter {chapter_number} file not found")
            return False
        
        try:
            with open(chapter_file, 'r', encoding='utf-8') as f:
                chapter_words = json.load(f)
            
            self.chapter_data[chapter_number] = chapter_words
            self.loaded_chapters.add(chapter_number)
            self.chapter_file_loads += 1
            
            # Build cache for this chapter
            self._build_chapter_cache(chapter_number, chapter_words)
            
            print(f"Loaded chapter {chapter_number} ({len(chapter_words)} words)")
            return True
            
        except Exception as e:
            print(f"Error loading chapter {chapter_number}: {e}")
            return False
    
    def _build_chapter_cache(self, chapter_number: int, chapter_words: List[Dict]):
        """Build lookup cache for a specific chapter"""
        chapter_cache = {}
        
        for i, word in enumerate(chapter_words):
            verse = word['verse']
            position = word['word_number_in_verse']
            cache_key = f"{verse}:{position}"
            chapter_cache[cache_key] = i
        
        self.chapter_caches[chapter_number] = chapter_cache
    
    def _build_lookup_indices(self):
        """Build optimization indices for faster word lookup (legacy single file)"""
        current_chapter = None
        
        for i, word in enumerate(self.word_data):
            chapter = word['chapter']
            verse = word['verse'] 
            position = word['word_number_in_verse']
            
            # Build chapter:verse:position -> index cache
            key = f"{chapter}:{verse}:{position}"
            self.word_lookup_cache[key] = i
            
            # Track chapter start indices
            if current_chapter != chapter:
                if chapter not in self.chapter_start_indices:
                    self.chapter_start_indices[chapter] = i
                current_chapter = chapter
    
    def get_word_by_sequence(self, sequence_number: int) -> Optional[Dict]:
        """Get word data by global sequence number"""
        if sequence_number <= 0 or sequence_number > len(self.word_data):
            return None
        return self.word_data[sequence_number - 1]
    
    def fetch_page_html(self, page_number: int) -> str:
        """Fetch HTML content for a specific page"""
        url = f"{self.base_url}?page={page_number}"
        try:
            response = requests.get(url)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            print(f"Error fetching page {page_number}: {e}")
            return ""
    
    def parse_line_type(self, line_div) -> str:
        """Determine the type of line based on CSS classes"""
        line_classes = line_div.get('class', [])
        
        if 'line--surah-name' in line_classes:
            return 'surah_name'
        elif 'line---bismillah' in line_classes:
            return 'bismillah'
        else:
            return 'ayah'
    
    def extract_surah_number(self, line_div) -> Optional[int]:
        """Extract surah number from surah name line"""
        # Look for surah icon with pattern like "surah020"
        surah_icon = line_div.find('span', class_='surah-name-v4-icon')
        if surah_icon:
            text = surah_icon.get_text(strip=True)
            match = re.search(r'surah(\d+)', text)
            if match:
                return int(match.group(1))
        return None
    
    def extract_word_info(self, word_span, page_number: int = None, line_number: int = None) -> Tuple[Optional[int], Optional[str], Optional[str]]:
        """Extract word sequence number with smart fallback for verse endings"""
        # Get data attributes
        data_location = word_span.get('data-location', '')
        data_position = word_span.get('data-position', '')
        
        # Check if this is likely a verse ending/sign (often has char-end class)
        is_verse_ending = 'char-end' in word_span.get('class', [])
        
        # Calculate global word sequence number using chapter-based lookup
        if data_location and data_position:
            parts = data_location.split(':')
            if len(parts) >= 2:
                chapter = int(parts[0])
                verse = int(parts[1])
                position = int(data_position) if data_position else 1
                
                self.total_lookups += 1
                
                # Try direct lookup first
                global_index = None
                if self.word_data_dir:
                    global_index = self._find_word_chapter_based(chapter, verse, position)
                else:
                    # Legacy single file lookup
                    cache_key = f"{chapter}:{verse}:{position}"
                    if cache_key in self.word_lookup_cache:
                        self.cache_hits += 1
                        index = self.word_lookup_cache[cache_key]
                        global_index = index + 1
                    else:
                        index = self._find_word_optimized(chapter, verse, position)
                        if index is not None:
                            global_index = index + 1
                
                # If direct lookup failed and it might be a verse ending, try smart fallback
                if global_index is None and is_verse_ending:
                    global_index = self._try_fallback_matching(chapter, verse, position, word_span)
                    
                    if global_index is None:
                        # Log validation issue
                        issue = ValidationIssue(
                            page_number=page_number or 0,
                            line_number=line_number or 0,
                            issue_type="verse_ending_not_found",
                            description=f"Verse ending sign not found: {data_location}:{position}",
                            data_location=data_location,
                            suggested_fix="Check if this is a pause mark or verse ending sign",
                            html_context=str(word_span)[:200]
                        )
                        self.validation_issues.append(issue)
                
                if global_index is not None:
                    return global_index, data_location, data_position
        
        return None, data_location, data_position
    
    def _try_fallback_matching(self, chapter: int, verse: int, position: int, word_span) -> Optional[int]:
        """Try smart fallback matching for verse endings and signs"""
        
        # Strategy 1: Try previous position (verse ending might be after last word)
        if position > 1:
            prev_index = None
            if self.word_data_dir:
                prev_index = self._find_word_chapter_based(chapter, verse, position - 1)
            else:
                cache_key = f"{chapter}:{verse}:{position - 1}"
                if cache_key in self.word_lookup_cache:
                    prev_index = self.word_lookup_cache[cache_key] + 1
            
            if prev_index:
                self.fallback_matches += 1
                # Return the position after the previous word (verse ending position)
                return prev_index + 1
        
        # Strategy 2: Check if this is the last position of the verse
        # Try to find the last word of this verse
        if self.word_data_dir and chapter in self.chapter_data:
            chapter_words = self.chapter_data[chapter]
            last_word_of_verse = None
            
            for i, word in enumerate(chapter_words):
                if word['verse'] == verse:
                    last_word_of_verse = i
                elif word['verse'] > verse:
                    break
            
            if last_word_of_verse is not None:
                self.fallback_matches += 1
                # Return position after last word (verse ending)
                return self._calculate_global_position(chapter, last_word_of_verse) + 1
        
        # Strategy 3: Check if it's actually the first word of next verse
        next_verse_index = None
        if self.word_data_dir:
            next_verse_index = self._find_word_chapter_based(chapter, verse + 1, 1)
        else:
            cache_key = f"{chapter}:{verse + 1}:1"
            if cache_key in self.word_lookup_cache:
                next_verse_index = self.word_lookup_cache[cache_key] + 1
        
        if next_verse_index:
            self.fallback_matches += 1
            # Return position before next verse (verse ending)
            return next_verse_index - 1
        
        return None
    
    def _find_word_chapter_based(self, chapter: int, verse: int, position: int) -> Optional[int]:
        """Find word using chapter-based file system (most efficient)"""
        
        # Load chapter on demand if not already loaded
        if chapter not in self.loaded_chapters:
            if not self._load_chapter(chapter):
                return None
        
        # Try chapter cache first (O(1) within chapter)
        if chapter in self.chapter_caches:
            cache_key = f"{verse}:{position}"
            if cache_key in self.chapter_caches[chapter]:
                self.cache_hits += 1
                chapter_index = self.chapter_caches[chapter][cache_key]
                
                # Calculate global position
                global_index = self._calculate_global_position(chapter, chapter_index)
                return global_index
        
        # Direct search within chapter (very fast since chapter is small)
        if chapter in self.chapter_data:
            chapter_words = self.chapter_data[chapter]
            for i, word in enumerate(chapter_words):
                if (word['verse'] == verse and word['word_number_in_verse'] == position):
                    self.sequential_hits += 1
                    
                    # Update cache for future lookups
                    if chapter not in self.chapter_caches:
                        self.chapter_caches[chapter] = {}
                    cache_key = f"{verse}:{position}"
                    self.chapter_caches[chapter][cache_key] = i
                    
                    # Calculate global position
                    global_index = self._calculate_global_position(chapter, i)
                    return global_index
        
        return None
    
    def _calculate_global_position(self, chapter: int, chapter_index: int) -> int:
        """Calculate global word position from chapter and index within chapter"""
        # For chapter-based system, we need to calculate the offset
        # This is an approximation - you might need to adjust based on your actual data structure
        
        # Simple approach: use the global_word_sequence_number from the word data if available
        if chapter in self.chapter_data and chapter_index < len(self.chapter_data[chapter]):
            word = self.chapter_data[chapter][chapter_index]
            if 'global_word_sequence_number' in word:
                return word['global_word_sequence_number']
        
        # Fallback: estimate based on chapter and position
        # This is a rough estimate - you might need to implement actual counting
        estimated_words_before = (chapter - 1) * 100  # Rough estimate
        return estimated_words_before + chapter_index + 1
    
    def _find_word_optimized(self, chapter: int, verse: int, position: int) -> Optional[int]:
        """Optimized word search using multiple strategies"""
        
        # Strategy 1: Sequential search from last matched index (most common case)
        for i in range(self.last_matched_index, len(self.word_data)):
            word = self.word_data[i]
            if (word['chapter'] == chapter and 
                word['verse'] == verse and 
                word['word_number_in_verse'] == position):
                self.last_matched_index = i
                self.sequential_hits += 1
                return i
        
        # Strategy 2: Search from chapter start if we have the index
        if chapter in self.chapter_start_indices:
            chapter_start = self.chapter_start_indices[chapter]
            
            # Search within this chapter (likely to be much smaller range)
            for i in range(chapter_start, len(self.word_data)):
                word = self.word_data[i]
                
                # Stop if we've moved to next chapter
                if word['chapter'] > chapter:
                    break
                    
                if (word['chapter'] == chapter and 
                    word['verse'] == verse and 
                    word['word_number_in_verse'] == position):
                    self.last_matched_index = i
                    self.chapter_search_hits += 1
                    return i
        
        # Strategy 3: Search before last matched index (rare case for non-sequential access)
        for i in range(0, self.last_matched_index):
            word = self.word_data[i]
            if (word['chapter'] == chapter and 
                word['verse'] == verse and 
                word['word_number_in_verse'] == position):
                self.backward_search_hits += 1
                # Don't update last_matched_index for backward searches
                return i
        
        return None
    
    def _get_bismillah_words(self, chapter: int) -> Tuple[Optional[int], Optional[int]]:
        """Get first and last word numbers for Bismillah of a chapter using optimized lookup"""
        
        if self.word_data_dir:
            # Chapter-based approach
            return self._get_bismillah_words_chapter_based(chapter)
        else:
            # Legacy single file approach
            return self._get_bismillah_words_legacy(chapter)
    
    def _get_bismillah_words_chapter_based(self, chapter: int) -> Tuple[Optional[int], Optional[int]]:
        """Get Bismillah words using chapter-based files"""
        
        # Load chapter if not already loaded
        if chapter not in self.loaded_chapters:
            if not self._load_chapter(chapter):
                return None, None
        
        if chapter not in self.chapter_data:
            return None, None
        
        chapter_words = self.chapter_data[chapter]
        bismillah_global_indices = []
        
        # Look for first 4 words of verse 1 (typical Bismillah)
        for word in chapter_words:
            if word['verse'] == 1 and word['word_number_in_verse'] <= 4:
                global_index = self._calculate_global_position(chapter, chapter_words.index(word))
                bismillah_global_indices.append(global_index)
            elif word['verse'] > 1:
                break  # Stop after verse 1
        
        if bismillah_global_indices:
            return bismillah_global_indices[0], bismillah_global_indices[-1]
        
        return None, None
    
    def _get_bismillah_words_legacy(self, chapter: int) -> Tuple[Optional[int], Optional[int]]:
        """Get Bismillah words using legacy single file approach"""
        # Try cache-based lookup first
        bismillah_indices = []
        for position in range(1, 5):  # Bismillah is typically 4 words
            cache_key = f"{chapter}:1:{position}"
            if cache_key in self.word_lookup_cache:
                bismillah_indices.append(self.word_lookup_cache[cache_key] + 1)
            else:
                break  # If one is missing, likely no more Bismillah words
        
        if bismillah_indices:
            return bismillah_indices[0], bismillah_indices[-1]
        
        # Fallback: search from chapter start (much more efficient than full scan)
        if chapter in self.chapter_start_indices:
            chapter_start = self.chapter_start_indices[chapter]
            bismillah_words = []
            
            # Look only in the first few words of the chapter
            search_limit = min(chapter_start + 20, len(self.word_data))  # Limit search scope
            
            for i in range(chapter_start, search_limit):
                word = self.word_data[i]
                
                # Stop if we've moved beyond verse 1
                if word['chapter'] != chapter or word['verse'] > 1:
                    break
                    
                if word['verse'] == 1 and word['word_number_in_verse'] <= 4:
                    bismillah_words.append(i + 1)
            
            if bismillah_words:
                return bismillah_words[0], bismillah_words[-1]
        
        return None, None
    
    def parse_ayah_line(self, line_div, page_number: int = None, line_number: int = None) -> Tuple[Optional[int], Optional[int], Optional[int], Optional[int]]:
        """Parse an ayah line and return first/last word numbers and chapter/verse info"""
        first_word_num = None
        last_word_num = None
        chapter_num = None
        verse_num = None
        
        # Find all word spans (including end markers for better handling)
        word_spans = line_div.find_all('span', class_=re.compile(r'char-word'))
        
        for word_span in word_spans:
            # Process all words including end markers
            word_seq, location, position = self.extract_word_info(word_span, page_number, line_number)
            
            if word_seq:
                if first_word_num is None:
                    first_word_num = word_seq
                last_word_num = word_seq
                
                # Extract chapter and verse from location
                if location:
                    parts = location.split(':')
                    if len(parts) >= 2:
                        if chapter_num is None:
                            chapter_num = int(parts[0])
                            verse_num = int(parts[1])
        
        return first_word_num, last_word_num, chapter_num, verse_num
    
    def parse_page(self, page_number: int):
        """Parse a single page and extract line mappings"""
        html_content = self.fetch_page_html(page_number)
        if not html_content:
            return
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Find the page div
        page_div = soup.find('div', id=f'page-{page_number}')
        if not page_div:
            print(f"Page {page_number} not found")
            return
        
        # Find all line containers
        line_containers = page_div.find_all('div', class_='line-container')
        
        current_chapter = None
        
        for line_container in line_containers:
            line_number = int(line_container.get('data-line', 0))
            if line_number == 0:
                continue
                
            line_div = line_container.find('div', class_='line')
            if not line_div:
                continue
            
            line_type = self.parse_line_type(line_div)
            
            if line_type == 'surah_name':
                # Extract surah number
                surah_num = self.extract_surah_number(line_div)
                if surah_num:
                    current_chapter = surah_num
                
                mapping = LineMapping(
                    page_number=page_number,
                    line_number=line_number,
                    line_type=line_type,
                    first_word_number=None,
                    last_word_number=None,
                    chapter_number=current_chapter
                )
                
            elif line_type == 'bismillah':
                # Bismillah is typically verse 1 of the chapter (except for chapter 9)
                # We need to find the word numbers for Bismillah
                if current_chapter and current_chapter != 9:
                    # Use optimized lookup for Bismillah words
                    first_word, last_word = self._get_bismillah_words(current_chapter)
                else:
                    first_word = None
                    last_word = None
                
                mapping = LineMapping(
                    page_number=page_number,
                    line_number=line_number,
                    line_type=line_type,
                    first_word_number=first_word,
                    last_word_number=last_word,
                    chapter_number=current_chapter
                )
                
            else:  # ayah line
                first_word, last_word, chapter, verse = self.parse_ayah_line(line_div, page_number, line_number)
                
                # Update current chapter if found
                if chapter:
                    current_chapter = chapter
                
                # Check for validation issues in ayah lines
                if first_word is None and last_word is None:
                    issue = ValidationIssue(
                        page_number=page_number,
                        line_number=line_number,
                        issue_type="empty_ayah_line",
                        description="Ayah line found but no words could be mapped",
                        html_context=str(line_div)[:300]
                    )
                    self.validation_issues.append(issue)
                
                mapping = LineMapping(
                    page_number=page_number,
                    line_number=line_number,
                    line_type=line_type,
                    first_word_number=first_word,
                    last_word_number=last_word,
                    chapter_number=current_chapter,
                    verse_number=verse
                )
            
            self.line_mappings.append(mapping)
            
            # Debug output
            print(f"Page {page_number}, Line {line_number}: {line_type}, "
                  f"Words: {mapping.first_word_number}-{mapping.last_word_number}, "
                  f"Chapter: {mapping.chapter_number}")
    
    def parse_pages(self, start_page: int, end_page: int):
        """Parse multiple pages"""
        for page_num in range(start_page, end_page + 1):
            print(f"\nParsing page {page_num}...")
            self.parse_page(page_num)
    
    def save_mappings(self, output_file: str):
        """Save line mappings to JSON file"""
        # Convert dataclass objects to dictionaries, excluding None values
        mappings_dict = []
        for mapping in self.line_mappings:
            d = asdict(mapping)
            # Remove verse_number if not needed in output
            if 'verse_number' in d:
                del d['verse_number']
            # Keep None values as they are meaningful
            mappings_dict.append(d)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(mappings_dict, f, ensure_ascii=False, indent=2)
        
        print(f"\nSaved {len(self.line_mappings)} line mappings to {output_file}")
    
    def save_validation_issues(self, output_file: str = None):
        """Save validation issues to a JSON file for manual review"""
        if not output_file:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"validation_issues_{timestamp}.json"
        
        # Group issues by type for easier review
        grouped_issues = {}
        for issue in self.validation_issues:
            issue_type = issue.issue_type
            if issue_type not in grouped_issues:
                grouped_issues[issue_type] = []
            grouped_issues[issue_type].append(asdict(issue))
        
        # Create summary
        summary = {
            "total_issues": len(self.validation_issues),
            "issues_by_type": {k: len(v) for k, v in grouped_issues.items()},
            "timestamp": datetime.now().isoformat(),
            "issues": grouped_issues
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        
        print(f"\nSaved {len(self.validation_issues)} validation issues to {output_file}")
        print("Issue types:")
        for issue_type, count in summary["issues_by_type"].items():
            print(f"  - {issue_type}: {count} issues")
        
        return output_file
    
    def validate_mappings(self):
        """Validate the parsed mappings for consistency"""
        internal_issues = []
        
        for i, mapping in enumerate(self.line_mappings):
            if mapping.line_type == 'ayah':
                # Check word number consistency
                if mapping.first_word_number and mapping.last_word_number:
                    if mapping.first_word_number > mapping.last_word_number:
                        internal_issues.append(f"Line {i}: first_word > last_word")
                        issue = ValidationIssue(
                            page_number=mapping.page_number,
                            line_number=mapping.line_number,
                            issue_type="word_order_error",
                            description=f"First word ({mapping.first_word_number}) > Last word ({mapping.last_word_number})",
                            suggested_fix="Check word order or verse boundaries"
                        )
                        self.validation_issues.append(issue)
                
                # Check for missing word mappings
                elif mapping.first_word_number is None or mapping.last_word_number is None:
                    internal_issues.append(f"Line {i}: Missing word mapping")
                    issue = ValidationIssue(
                        page_number=mapping.page_number,
                        line_number=mapping.line_number,
                        issue_type="missing_word_mapping",
                        description="Ayah line has incomplete word mappings",
                        suggested_fix="Check HTML structure or word data availability"
                    )
                    self.validation_issues.append(issue)
        
        # Print summary
        if internal_issues:
            print(f"\nValidation found {len(internal_issues)} consistency issues")
            for issue in internal_issues[:5]:  # Show first 5 issues
                print(f"  - {issue}")
            if len(internal_issues) > 5:
                print(f"  ... and {len(internal_issues) - 5} more")
        else:
            print("\nValidation passed - no consistency issues!")
        
        # Save validation issues if any exist
        if self.validation_issues:
            issues_file = self.save_validation_issues()
            print(f"\n⚠️  {len(self.validation_issues)} validation issues saved for review")
            print(f"   Review file: {issues_file}")
        
        return len(internal_issues) == 0
    
    def print_performance_stats(self):
        """Print performance statistics for optimization analysis"""
        if self.total_lookups == 0:
            print("No lookups performed yet.")
            return
            
        print("\n" + "="*50)
        print("PERFORMANCE STATISTICS")
        print("="*50)
        print(f"Total word lookups: {self.total_lookups:,}")
        
        if self.word_data_dir:
            # Chapter-based statistics
            print(f"Chapters loaded: {len(self.loaded_chapters)} chapters")
            print(f"Chapter file loads: {self.chapter_file_loads}")
            print(f"Cache hits: {self.cache_hits:,} ({self.cache_hits/self.total_lookups*100:.1f}%)")
            print(f"Sequential hits (within chapter): {self.sequential_hits:,} ({self.sequential_hits/self.total_lookups*100:.1f}%)")
            print(f"Fallback matches (verse endings): {self.fallback_matches:,} ({self.fallback_matches/self.total_lookups*100:.1f}%)")
            
            # Memory efficiency
            total_words_loaded = sum(len(words) for words in self.chapter_data.values())
            print(f"Words in memory: {total_words_loaded:,} (vs ~80,000 total)")
            memory_efficiency = (1 - total_words_loaded / 80000) * 100 if total_words_loaded > 0 else 0
            print(f"Memory saved: ~{memory_efficiency:.1f}%")
            
        else:
            # Legacy single file statistics  
            print(f"Cache hits: {self.cache_hits:,} ({self.cache_hits/self.total_lookups*100:.1f}%)")
            print(f"Sequential search hits: {self.sequential_hits:,} ({self.sequential_hits/self.total_lookups*100:.1f}%)")
            print(f"Chapter search hits: {self.chapter_search_hits:,} ({self.chapter_search_hits/self.total_lookups*100:.1f}%)")
            print(f"Backward search hits: {self.backward_search_hits:,} ({self.backward_search_hits/self.total_lookups*100:.1f}%)")
        
        # Calculate efficiency
        fast_lookups = self.cache_hits + self.sequential_hits
        print(f"\nOptimization efficiency: {fast_lookups/self.total_lookups*100:.1f}%")
        
        if self.word_data_dir:
            print("Chapter-based loading: Extreme memory efficiency + O(1) lookups within chapters")
            avg_chapter_size = sum(len(words) for words in self.chapter_data.values()) / max(len(self.chapter_data), 1)
            print(f"Average chapter size: ~{avg_chapter_size:.0f} words (vs 80,000 full dataset)")
        else:
            total_words = len(self.word_data) if self.word_data else 80000
            avoided = total_words - (self.total_lookups - self.cache_hits)
            print(f"Average lookups avoided per word: {avoided:,}")
        
        if self.cache_hits > 0:
            print("Cache effectiveness: Perfect O(1) lookup")
        if self.sequential_hits > 0 and self.word_data_dir:
            print("Sequential search: Within small chapter boundaries (very fast)")


def main():
    """Main function to run the parser"""
    parser = QuranParser()
    
    # Load word data - now supports both directory and single file
    # For chapter-based files: pass directory containing 1.json, 2.json, ... 114.json
    word_data_path = "en/wbw/"  # Directory with chapter files
    # OR for single file: word_data_path = "quran_words.json" 
    
    parser.load_word_data(word_data_path)
    
    # Parse pages (adjust range as needed)
    start_page = 1
    end_page = 610  # Parse first 10 pages as example
    
    parser.parse_pages(start_page, end_page)
    
    # Print performance statistics
    parser.print_performance_stats()
    
    # Validate mappings
    parser.validate_mappings()
    
    # Save results
    output_file = "line_mappings.json"
    parser.save_mappings(output_file)
    
    # Print summary
    print("\n" + "="*50)
    print("SUMMARY")
    print("="*50)
    print(f"Total lines parsed: {len(parser.line_mappings)}")
    
    # Count by type
    type_counts = {}
    for mapping in parser.line_mappings:
        type_counts[mapping.line_type] = type_counts.get(mapping.line_type, 0) + 1
    
    for line_type, count in type_counts.items():
        print(f"  {line_type}: {count}")


if __name__ == "__main__":
    main()