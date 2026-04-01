"""Arabic military benchmark corpus for ALLaM quality checks."""

MILITARY_ARABIC_TEST_SET = {
    "summarization": [
        {
            "input": "رصدت وحدة المراقبة البحرية حركة مشبوهة لسفينة مجهولة الهوية في المنطقة الاقتصادية الخالصة بالقرب من مضيق باب المندب. السفينة أوقفت نظام التعرف التلقائي قبل ثلاث ساعات وتتحرك بسرعة منخفضة باتجاه الساحل اليمني.",
            "expected_summary_contains": ["سفينة", "باب المندب", "مشبوهة"],
            "language": "ar",
        },
        {
            "input": "أعلنت القيادة المشتركة عن بدء تمرين درع الخليج المشترك مع قوات دولة الإمارات العربية المتحدة. يتضمن التمرين عمليات برية وبحرية وجوية مشتركة في المنطقة الشرقية لمدة أسبوعين.",
            "expected_summary_contains": ["تمرين", "درع الخليج", "الإمارات"],
            "language": "ar",
        },
    ],
    "entity_extraction": [
        {
            "input": "تقدمت الكتيبة الأولى مدرعات من لواء الملك عبدالعزيز باتجاه منطقة نجران بعد رصد تحركات معادية على الحدود الجنوبية.",
            "expected_entities": [
                {"type": "UNIT", "value": "الكتيبة الأولى مدرعات"},
                {"type": "UNIT", "value": "لواء الملك عبدالعزيز"},
                {"type": "LOCATION", "value": "نجران"},
                {"type": "LOCATION", "value": "الحدود الجنوبية"},
            ],
        }
    ],
    "translation": [
        {"ar": "طلب دعم جوي فوري", "en": "Request immediate air support"},
        {"ar": "عودة جميع الوحدات للقاعدة", "en": "All units return to base"},
        {"ar": "رصد طائرة معادية بدون طيار", "en": "Hostile unmanned aerial vehicle detected"},
        {"ar": "تقرير موقف المنطقة الشرقية", "en": "Eastern sector situation report"},
        {"ar": "تأمين مضيق هرمز", "en": "Secure the Strait of Hormuz"},
    ],
    "command_classification": [
        {"input": "أرسل طائرتين بدون طيار لاستطلاع الشبكة ٥٠٠،٣٠٠", "expected_intent": "MOVE_UNIT"},
        {"input": "ما هو مستوى التهديد في القطاع ألفا؟", "expected_intent": "QUERY_THREATS"},
        {"input": "اشتبك مع الهدف المعادي على سمت ٠٤٥", "expected_intent": "ENGAGE_TARGET"},
        {"input": "أنشئ تقرير موقف للبحر الأحمر", "expected_intent": "GENERATE_REPORT"},
    ],
}
