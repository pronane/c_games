// tiny JSON reader (objects -> Dictionary<string, object>, arrays -> List<object>, numbers -> double)
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace SpriteForge.Editor
{
    public static class SFJson
    {
        public static object Parse(string s) { int i = 0; var v = Value(s, ref i); return v; }

        static void Ws(string s, ref int i) { while (i < s.Length && char.IsWhiteSpace(s[i])) i++; }

        static object Value(string s, ref int i)
        {
            Ws(s, ref i);
            char c = s[i];
            if (c == '{')
            {
                var d = new Dictionary<string, object>(); i++;
                Ws(s, ref i);
                if (s[i] == '}') { i++; return d; }
                while (true)
                {
                    Ws(s, ref i); var k = Str(s, ref i); Ws(s, ref i); i++; // ':'
                    d[k] = Value(s, ref i); Ws(s, ref i);
                    if (s[i] == ',') { i++; continue; }
                    i++; return d;                                          // '}'
                }
            }
            if (c == '[')
            {
                var l = new List<object>(); i++;
                Ws(s, ref i);
                if (s[i] == ']') { i++; return l; }
                while (true)
                {
                    l.Add(Value(s, ref i)); Ws(s, ref i);
                    if (s[i] == ',') { i++; continue; }
                    i++; return l;
                }
            }
            if (c == '"') return Str(s, ref i);
            if (s.Substring(i).StartsWith("true")) { i += 4; return true; }
            if (s.Substring(i).StartsWith("false")) { i += 5; return false; }
            if (s.Substring(i).StartsWith("null")) { i += 4; return null; }
            int st = i;
            while (i < s.Length && "+-0123456789.eE".IndexOf(s[i]) >= 0) i++;
            return double.Parse(s.Substring(st, i - st), CultureInfo.InvariantCulture);
        }

        static string Str(string s, ref int i)
        {
            var sb = new StringBuilder(); i++;
            while (s[i] != '"')
            {
                if (s[i] == '\\')
                {
                    i++;
                    char e = s[i];
                    if (e == 'n') sb.Append('\n');
                    else if (e == 't') sb.Append('\t');
                    else if (e == 'u') { sb.Append((char)Convert.ToInt32(s.Substring(i + 1, 4), 16)); i += 4; }
                    else sb.Append(e);
                }
                else sb.Append(s[i]);
                i++;
            }
            i++;
            return sb.ToString();
        }

        // helpers
        public static Dictionary<string, object> O(object o, string k) { return (Dictionary<string, object>)((Dictionary<string, object>)o)[k]; }
        public static List<object> L(object o, string k) { return (List<object>)((Dictionary<string, object>)o)[k]; }
        public static bool Has(object o, string k) { return o is Dictionary<string, object> && ((Dictionary<string, object>)o).ContainsKey(k); }
        public static double N(object o, string k, double dflt = 0) { var d = (Dictionary<string, object>)o; return d.ContainsKey(k) && d[k] is double ? (double)d[k] : dflt; }
        public static string S(object o, string k, string dflt = "") { var d = (Dictionary<string, object>)o; return d.ContainsKey(k) && d[k] != null ? d[k].ToString() : dflt; }
        public static bool B(object o, string k, bool dflt = false) { var d = (Dictionary<string, object>)o; return d.ContainsKey(k) && d[k] is bool ? (bool)d[k] : dflt; }
    }
}
