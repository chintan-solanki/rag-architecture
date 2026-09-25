import re

class CitationMatcher:

    def __init__(self):
        self.states = {
            'start' : {r'\[': '['},
            '[': {r'\[': '[['},
            '[[': {r'c': '[[c'},
            '[[c': {r'i': '[[ci'},
            '[[ci': {r't': '[[cit'},
            '[[cit': {r'e': '[[cite'},
            '[[cite': {r'\]': '[[cite]'},
            '[[cite]': {r'\]': '[[cite]]'},
            '[[cite]]': {r'\[': '[[cite]][_start'},
            '[[cite]][_start': {r'\d': '[[cite]][_id_matched'},
            '[[cite]][_id_matched': {
                r'\d': '[[cite]][_id_matched',
                r',': '[[cite]][_await_next_id',
                r']': 'end'
                },
            '[[cite]][_await_next_id': {r'\d': '[[cite]][_id_matched'},
            'end' : {r'\[': '['},
        }

        self.state = 'start'
        self.consumed_cnt = 0

    def addchar(self, ch):

        transitions = self.states[self.state]
        matched = False
        
        for pattern, nextstate in transitions.items():
            if re.match(pattern, ch):
                matched = True
                self.consumed_cnt += 1
                self.state = nextstate
                break

        if not matched:
            self.state = 'start'
            self.consumed_cnt = 0

class CitationProcessor:

    def __init__(self):
        
        self.target_text = ''
        self.partial_matched_str = ''
        self.curr_target_block_start_index = 0
        self.all_citations = []

        self.partial_matcher = CitationMatcher()

    def _get_citation_ids(self, citation_block = ''):
        source_ids = []
        matchobj = re.match(r'\[\[cite\]\]\[(.*)\]', citation_block)
        if matchobj and matchobj.group(1):

            source_ids_str = matchobj.group(1)
            source_ids = [int(id_str) for id_str in source_ids_str.split(',') if len(id_str) > 0]

        return source_ids

        
    def add_chunk(self, src_chunk: str):

        if not src_chunk:
            return ''

        extracted_str = ''

        for ch in src_chunk:
            
            self.partial_matcher.addchar(ch)

            curr_state, consumed_cnt = self.partial_matcher.state, self.partial_matcher.consumed_cnt

            # if complete citation pattern found
            if curr_state == 'end':   
                
                #retrieve citation ids
                citation_block = self.partial_matched_str + ch
                citation_ids = self._get_citation_ids(citation_block)

                curr_block_end_index = len(self.target_text) + len(extracted_str) 

                citation_obj = (
                    self.curr_target_block_start_index, 
                    curr_block_end_index,
                    citation_ids
                )

                self.all_citations.append(citation_obj)
                self.curr_target_block_start_index = curr_block_end_index

                self.partial_matched_str = ''

            # if partial citation pattern matched 
            elif curr_state != 'start': 
                
                self.partial_matched_str += ch

            # not even partial match to citation pattern
            else:
                #add partial text matched so far to extracted text and reset it
                extracted_str += self.partial_matched_str 
                self.partial_matched_str = ''

                #add new char to extracted text
                extracted_str += ch

        #add extracted str to target text
        self.target_text += extracted_str

        #return the extracted str
        return extracted_str
                
    def end_src_stream(self):
        self.target_text += self.partial_matched_str


if __name__ == '__main__':
    chunks = ["Tr" , "um" ,  "or" ,  "GPT" ,  " is" , " a" ,  " specialized" , " language" , " model" , " designed" , " to" , " address" ,     " health" ,     " and" ,     " medical" ,     " misinformation" ,     "." ,     " It" ,     " incorporates" ,     " domain" ,     "-specific" ,     " knowledge" ,     "," ,     " particularly" ,     " through" ,     " the" ,     " use" ,     " of" ,     " semantic" ,     " health" ,     " knowledge" ,     " graphs" ,     "," ,     " which" ,     " allows" ,     " it" ,     " to" ,     " identify" ,     " nuances" ,     " in" ,     " health" ,     "-related" ,     " claims" ,     " effectively" ,     "." ,     " This" ,     " specialization" ,     " enhances" ,     " its" ,     " accuracy" ,     " and" ,     " reliability" ,     " in" ,     " fact" ,     "-check" ,     "ing" ,     " health" ,     " information" ,     " " ,  "[[cite]]" ,     "[1" ,     ",2]." ,     " Additionally" ,     "," ,     " Tr" ,     "um" ,     "or" ,     "GPT" ,     " is" ,  " noted" , " for" , " its" , " efficiency" , "," , " generating" , " concise" , " responses" , " with" , " an" , " average" , " of" , " " , "2" ,  "." , "8" , " sentences" ,  "," , " which" , " is" , " lower" , " than" ,  " other" , " models" , " evaluated" ,  "." , " This" , " conc" ,  "isen" ,  "ess" ,  " aids" ,  " users" , " in" ,  " quickly" ,  " understanding" ,  " fact" , "-check" , "ing" ,  " results" ,  " without" , " excessive" , " detail" ,  " " ,  "[[cite]]" ,  "[1" ,  "]." ]
    
    processor = CitationProcessor()

    for chunk in chunks:
        processor.add_chunk(chunk)

    processor.end_src_stream()

    print(processor.target_text)
    print(processor.all_citations)        
    
    
