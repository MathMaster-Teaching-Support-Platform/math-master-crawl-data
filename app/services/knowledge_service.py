import json
import os
from typing import List, Dict, Any, Optional
import re
from pathlib import Path
from app.core.config import settings

class KnowledgeService:
    def __init__(self):
        self.knowledge_base = None
        self.load_knowledge_base()
        # Build intent_keywords mapping from all keys in knowledge_base.json that có 'keywords'
        current_dir = Path(__file__).parent.parent
        kb_path = current_dir / "data" / "knowledge_base.json"
        with open(kb_path, 'r', encoding='utf-8') as f:
            self.kb_json = json.load(f)
        self.intent_keywords = {k: v["keywords"] for k, v in self.kb_json.items() if isinstance(v, dict) and "keywords" in v}
        self.school_keywords = self.kb_json.get("school_recommendation", {}).get("keywords", [])
        self.major_keywords = self.kb_json.get("major_advice", {}).get("keywords", [])

    def load_knowledge_base(self):
        """Load knowledge base từ file JSON"""
        try:
            # Tìm đường dẫn file knowledge base
            current_dir = Path(__file__).parent.parent
            kb_path = current_dir / "data" / "knowledge_base.json"

            if not kb_path.exists():
                print(f"Knowledge base file not found at {kb_path}")
                self.knowledge_base = {}
                return

            with open(kb_path, 'r', encoding='utf-8') as f:
                self.knowledge_base = json.load(f)
            print(f"✅ Loaded knowledge base with {len(self.knowledge_base)} categories")

        except Exception as e:
            print(f"Error loading knowledge base: {e}".encode('ascii', errors='replace').decode('ascii'))
            self.knowledge_base = {}
    
    def search_by_intent(self, intent: str) -> Dict[str, Any]:
        """Lấy thông tin theo intent"""
        if not self.knowledge_base:
            return {}
        
        return self.knowledge_base.get(intent, {})
    
    def search_by_keywords(self, message: str, limit: int = 3) -> List[Dict[str, Any]]:
        """Tìm kiếm thông tin dựa trên keywords trong tin nhắn"""
        if not self.knowledge_base:
            return []
        
        message_lower = message.lower()
        results = []
        
        for category_key, keywords in self.intent_keywords.items():
            matches = sum(1 for keyword in keywords if keyword in message_lower)
            if matches > 0:
                results.append({
                    'category': category_key,
                    'relevance_score': matches,
                    'data': self.knowledge_base.get(category_key, {})
                })
        
        # Sắp xếp theo độ relevance và trả về top results
        results.sort(key=lambda x: x['relevance_score'], reverse=True)
        return results[:limit]
    
    def get_school_info(self, school_name: str) -> Optional[Dict[str, Any]]:
        """Tìm thông tin trường học cụ thể"""
        if not self.knowledge_base:
            return None
        
        school_info = self.knowledge_base.get('school_info', {})
        sample_schools = school_info.get('sample_schools', {})
        
        # Tìm kiếm tên trường (flexible matching)
        school_name_clean = re.sub(r'[^\w\s]', '', school_name.lower())
        
        for school_key, school_data in sample_schools.items():
            school_data_name = re.sub(r'[^\w\s]', '', school_data.get('name', '').lower())
            if school_name_clean in school_data_name or school_data_name in school_name_clean:
                return school_data
        
        return None
    
    def get_major_info(self, major_name: str) -> Optional[Dict[str, Any]]:
        """Tìm thông tin ngành học"""
        if not self.knowledge_base:
            return None
        
        major_advice = self.knowledge_base.get('major_advice', {})
        hot_majors = major_advice.get('hot_majors_2024', {})
        
        # Flexible search cho tên ngành
        major_name_clean = major_name.lower()
        
        for major_key, major_data in hot_majors.items():
            if major_name_clean in major_key.lower() or major_key.lower() in major_name_clean:
                return {
                    'name': major_key,
                    **major_data
                }
        
        return None
    
    def get_admission_timeline(self) -> Dict[str, Any]:
        """Lấy lịch tuyển sinh"""
        if not self.knowledge_base:
            return {}
        
        return self.knowledge_base.get('schedules', {})
    
    def search_comprehensive(self, user_message: str, intent: str) -> Dict[str, Any]:
        """
        Tìm kiếm comprehensive để cung cấp context cho OpenAI
        """
        context = {
            'intent_data': self.search_by_intent(intent),
            'keyword_matches': self.search_by_keywords(user_message),
            'relevant_info': {}
        }
        
        # Tìm thông tin cụ thể dựa trên intent
        if intent == "school_recommendation":
            # Tìm tên trường trong message
            school_match = self._extract_school_name(user_message)
            if school_match:
                context['relevant_info']['school'] = self.get_school_info(school_match)
        
        elif intent == "major_advice":
            # Tìm tên ngành trong message
            major_match = self._extract_major_name(user_message)
            if major_match:
                context['relevant_info']['major'] = self.get_major_info(major_match)
        
        elif intent == "schedule":
            context['relevant_info']['timeline'] = self.get_admission_timeline()
        
        # Thêm FAQs liên quan
        if 'common_questions' in self.knowledge_base:
            context['relevant_info']['faqs'] = self._find_relevant_faqs(user_message)
        
        return context
    
    def _extract_school_name(self, message: str) -> Optional[str]:
        """Trích xuất tên trường từ tin nhắn"""
        message_lower = message.lower()
        for school in self.school_keywords:
            if school in message_lower:
                return school
        return None
    
    def _extract_major_name(self, message: str) -> Optional[str]:
        """Trích xuất tên ngành từ tin nhắn"""
        message_lower = message.lower()
        for major in self.major_keywords:
            if major in message_lower:
                return major
        return None
    
    def _find_relevant_faqs(self, message: str, limit: int = 2) -> List[Dict[str, str]]:
        """Tìm FAQs liên quan đến câu hỏi"""
        if 'common_questions' not in self.knowledge_base:
            return []
        
        faqs = self.knowledge_base['common_questions'].get('faqs', [])
        message_lower = message.lower()
        
        relevant_faqs = []
        for faq in faqs:
            question_lower = faq['question'].lower()
            
            # Kiểm tra từ khóa chung
            common_words = set(message_lower.split()) & set(question_lower.split())
            if len(common_words) >= 2:  # Ít nhất 2 từ khóa chung
                relevant_faqs.append(faq)
        
        return relevant_faqs[:limit]
    
    def get_score_analysis_context(self, student_data: Dict[str, Any]) -> Dict[str, Any]:
        """Phân tích điểm số và cung cấp context cho tư vấn"""
        if not student_data or not student_data.get('blocks'):
            return {}
        
        blocks = student_data.get('blocks', [])
        analysis = {
            'score_level': 'unknown',
            'recommendations': [],
            'suitable_schools': []
        }
        
        # Tìm điểm cao nhất
        max_score = 0
        best_block = None
        
        for block in blocks:
            point = block.get('point', 0)
            if point > max_score:
                max_score = point
                best_block = block
        
        # Phân tích mức điểm
        if max_score >= 27:
            analysis['score_level'] = 'excellent'
            analysis['suitable_schools'] = ['ĐHQG Hà Nội', 'ĐHQG TP.HCM', 'Bách Khoa Hà Nội']
        elif max_score >= 24:
            analysis['score_level'] = 'good'
            analysis['suitable_schools'] = ['ĐHQG Đà Nẵng', 'Kinh tế Quốc dân', 'Ngoại thương']
        elif max_score >= 21:
            analysis['score_level'] = 'average_good'
            analysis['suitable_schools'] = ['Đại học khu vực', 'Các trường top tỉnh']
        else:
            analysis['score_level'] = 'average'
            analysis['suitable_schools'] = ['Đại học tỉnh', 'Cao đẳng chất lượng cao']
        
        if best_block:
            analysis['best_block'] = {
                'name': best_block.get('label', ''),
                'score': best_block.get('point', 0),
                'subjects': best_block.get('subjects', [])
            }
        
        return analysis

    def get_smart_context(self, user_message: str, intent: str, chat_history: list = None) -> dict:
        """
        Intelligent context selection dựa trên:
        1. Current intent
        2. Previous conversation context  
        3. Extracted entities
        4. Chat history patterns
        """
        context = {
            'primary_context': self.search_by_intent(intent),
            'entities': self._extract_all_entities(user_message),
            'conversation_context': {},
            'relevant_data': {}
        }
        entities = context['entities']
        # School-specific context
        if entities.get('school_name'):
            school_info = self.get_school_info(entities['school_name'])
            if school_info:
                context['relevant_data']['school'] = school_info
        # Major-specific context  
        if entities.get('major_name'):
            major_info = self.get_major_info(entities['major_name'])
            if major_info:
                context['relevant_data']['major'] = major_info
        # Score-specific context
        if entities.get('score_mentioned'):
            score = entities['score_mentioned']
            context['relevant_data']['score_analysis'] = self._analyze_score_level(score)
        # Conversation history context
        if chat_history:
            context['conversation_context'] = self._analyze_conversation_patterns(chat_history)
        # Intent-specific smart additions
        if intent == "school_recommendation":
            if len(entities.get('schools', [])) > 1:
                context['relevant_data']['comparison'] = True
        elif intent == "major_advice":
            career_keywords = ["tương lai", "triển vọng", "việc làm", "lương"]
            if any(keyword in user_message.lower() for keyword in career_keywords):
                context['relevant_data']['career_focus'] = True
        return context

    def _extract_all_entities(self, message: str) -> dict:
        """Extract all possible entities from message"""
        entities = {}
        message_lower = message.lower()
        import re
        score_pattern = r'\b(\d{1,2}(?:\.\d{1,2})?)\s*(?:điểm|point)\b'
        scores = re.findall(score_pattern, message_lower)
        if scores:
            entities['score_mentioned'] = float(scores[0])
        school_patterns = [
            r'bách\s*khoa\s*(?:hà\s*nội|hn|hcm|tp\.hcm)?',
            r'đại\s*học\s*y\s*(?:hà\s*nội|hn|hcm)?',
            r'kinh\s*tế\s*quốc\s*dân',
            r'ngoại\s*thương',
            r'fpt\s*university',
            r'sư\s*phạm\s*(?:hà\s*nội|hn|hcm)?'
        ]
        found_schools = []
        for pattern in school_patterns:
            matches = re.findall(pattern, message_lower)
            found_schools.extend(matches)
        if found_schools:
            entities['schools'] = found_schools
            entities['school_name'] = found_schools[0]
        major_patterns = [
            r'công\s*nghệ\s*thông\s*tin|cntt|it',
            r'y\s*khoa|medicine',
            r'kinh\s*tế|economics',
            r'cơ\s*khí|mechanical',
            r'điện\s*tử|electronics',
            r'luật|law',
            r'sư\s*phạm|education'
        ]
        found_majors = []
        for pattern in major_patterns:
            if re.search(pattern, message_lower):
                found_majors.append(pattern.split('|')[0])
        if found_majors:
            entities['majors'] = found_majors
            entities['major_name'] = found_majors[0]
        location_patterns = [
            r'hà\s*nội|hn',
            r'tp\.?\s*hcm|sài\s*gòn|hcm',
            r'đà\s*nẵng|da\s*nang',
            r'cần\s*thơ',
            r'miền\s*bắc|north',
            r'miền\s*nam|south'
        ]
        for pattern in location_patterns:
            if re.search(pattern, message_lower):
                entities['location'] = pattern.split('|')[0]
                break
        return entities

    def _analyze_score_level(self, score: float) -> dict:
        """Analyze score level and provide context"""
        if score >= 27:
            return {
                'level': 'excellent',
                'description': 'Điểm xuất sắc',
                'opportunities': ['Top universities', 'Competitive majors', 'Scholarship eligible'],
                'advice': 'Có thể chọn bất kỳ trường/ngành nào'
            }
        elif score >= 24:
            return {
                'level': 'good', 
                'description': 'Điểm khá tốt',
                'opportunities': ['Good universities', 'Most majors available'],
                'advice': 'Nhiều lựa chọn tốt, cân nhắc sở thích'
            }
        elif score >= 21:
            return {
                'level': 'average_good',
                'description': 'Điểm trung bình khá',
                'opportunities': ['Regional universities', 'Selected majors'],
                'advice': 'Chọn cẩn thận theo cơ hội việc làm'
            }
        else:
            return {
                'level': 'average',
                'description': 'Điểm trung bình',
                'opportunities': ['Local universities', 'Vocational schools'],
                'advice': 'Cân nhắc cả đại học và cao đẳng'
            }

    def _analyze_conversation_patterns(self, chat_history: list) -> dict:
        """Phân tích các pattern trong lịch sử chat để hỗ trợ context thông minh"""
        if not chat_history:
            return {}
        intents = [msg.get("intent", "general") for msg in chat_history if isinstance(msg, dict)]
        intent_counts = {}
        for intent in intents:
            intent_counts[intent] = intent_counts.get(intent, 0) + 1
        mentioned_entities = {
            'candidate_numbers': [],
            'schools': [],
            'majors': [],
            'locations': []
        }
        for msg in chat_history:
            user_msg = msg.get("user_message", "")
            entities = self._extract_all_entities(user_msg)
            if entities.get('candidate_number'):
                mentioned_entities['candidate_numbers'].append(entities['candidate_number'])
            if entities.get('school_name'):
                mentioned_entities['schools'].append(entities['school_name'])
            if entities.get('major_name'):
                mentioned_entities['majors'].append(entities['major_name'])
            if entities.get('location'):
                mentioned_entities['locations'].append(entities['location'])
        for key in mentioned_entities:
            mentioned_entities[key] = list(set(mentioned_entities[key]))
        return {
            "intent_distribution": intent_counts,
            "mentioned_entities": mentioned_entities,
            "recent_intents": intents[-settings.chat_history_limit:] if len(intents) >= settings.chat_history_limit else intents
        }

# Singleton instance
knowledge_service = KnowledgeService()