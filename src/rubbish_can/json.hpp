// COPYING: Original version is from https://github.com/nbsdx/SimpleJSON.git
#pragma once

#include <cmath>
#include <cctype>
#include <string>
#include <deque>
#include <map>
#include <type_traits>
#include <initializer_list>
#include <ostream>
#include <iostream>
#include <cpptrace/cpptrace.hpp>
#include "colorful.hxx"

namespace json {

using std::map;
using std::deque;
using std::string;
using std::enable_if;
using std::initializer_list;
using std::is_same;
using std::is_convertible;
using std::is_integral;
using std::is_floating_point;

namespace {
    inline string json_escape( const string &str ) {
        string output;
        output.reserve( str.length() * 2 );
        for( unsigned i = 0; i < str.length(); ++i )
            switch( str[i] ) {
                case '\"': output += "\\\""; break;
                case '\\': output += "\\\\"; break;
                case '\b': output += "\\b";  break;
                case '\f': output += "\\f";  break;
                case '\n': output += "\\n";  break;
                case '\r': output += "\\r";  break;
                case '\t': output += "\\t";  break;
                default  : output += str[i]; break;
            }
        return output;
    }
}

class JSON
{
    union BackingData {
        BackingData( double d ) : Float( d ){}
        BackingData( long   l ) : Int( l ){}
        BackingData( bool   b ) : Bool( b ){}
        BackingData( string s ) : String( new string( s ) ){}
        BackingData()           : Int( 0 ){}

        deque<JSON>        *List;
        map<string,JSON>   *Map;
        string             *String;
        double              Float;
        long                Int;
        bool                Bool;
    } Internal;

    public:
        enum class Class {
            Null,
            Object,
            Array,
            String,
            Floating,
            Integral,
            Boolean
        };
        static std::string ClassString(Class type) {
            switch( type ) {
                case Class::Null:      return "Null";
                case Class::Object:    return "Object";
                case Class::Array:     return "Array";
                case Class::String:    return "String";
                case Class::Floating:  return "Floating";
                case Class::Integral:  return "Integral";
                case Class::Boolean:   return "Boolean";
                default:
                    colorful::printHONG( "JSON::ClassString: Unknown class %d.\n", static_cast<int>(type) );
                    cpptrace::generate_trace().print();
                    std::abort();
            }
        }

        template <typename Container>
        class JSONWrapper {
            Container *object;

            public:
                JSONWrapper( Container *val ) : object( val ) {}
                JSONWrapper( std::nullptr_t )  : object( nullptr ) {}

                typename Container::iterator begin() { return object ? object->begin() : typename Container::iterator(); }
                typename Container::iterator end() { return object ? object->end() : typename Container::iterator(); }
                typename Container::const_iterator begin() const { return object ? object->begin() : typename Container::iterator(); }
                typename Container::const_iterator end() const { return object ? object->end() : typename Container::iterator(); }
        };

        template <typename Container>
        class JSONConstWrapper {
            const Container *object;

            public:
                JSONConstWrapper( const Container *val ) : object( val ) {}
                JSONConstWrapper( std::nullptr_t )  : object( nullptr ) {}

                typename Container::const_iterator begin() const { return object ? object->begin() : typename Container::const_iterator(); }
                typename Container::const_iterator end() const { return object ? object->end() : typename Container::const_iterator(); }
        };

        JSON() : Internal(), Type( Class::Null ){}

        JSON( initializer_list<JSON> list ) 
            : JSON() 
        {
            SetType( Class::Object );
            for( auto i = list.begin(), e = list.end(); i != e; ++i, ++i )
                operator[]( i->ToString() ) = *std::next( i );
        }

        JSON( JSON&& other )
            : Internal( other.Internal )
            , Type( other.Type )
        {
            other.Type = Class::Null;
            other.Internal.Map = nullptr;
            other.Internal.String = nullptr;
            other.Internal.List = nullptr;
        }

        JSON& operator=( JSON&& other ) {
            ClearInternal();
            Internal = other.Internal;
            Type = other.Type;
            other.Internal.Map = nullptr;
            other.Internal.String = nullptr;
            other.Internal.List = nullptr;
            other.Type = Class::Null;
            return *this;
        }

        JSON( const JSON &other ) {
            switch( other.Type ) {
            case Class::Object:
                Internal.Map = 
                    new map<string,JSON>( other.Internal.Map->begin(),
                                          other.Internal.Map->end() );
                break;
            case Class::Array:
                Internal.List = 
                    new deque<JSON>( other.Internal.List->begin(),
                                      other.Internal.List->end() );
                break;
            case Class::String:
                Internal.String = 
                    new string( *other.Internal.String );
                break;
            default:
                Internal = other.Internal;
            }
            Type = other.Type;
        }

        JSON& operator=( const JSON &other ) {
            ClearInternal();
            switch( other.Type ) {
            case Class::Object:
                Internal.Map = 
                    new map<string,JSON>( other.Internal.Map->begin(),
                                          other.Internal.Map->end() );
                break;
            case Class::Array:
                Internal.List = 
                    new deque<JSON>( other.Internal.List->begin(),
                                      other.Internal.List->end() );
                break;
            case Class::String:
                Internal.String = 
                    new string( *other.Internal.String );
                break;
            default:
                Internal = other.Internal;
            }
            Type = other.Type;
            return *this;
        }

        ~JSON() {
            switch( Type ) {
            case Class::Array:
                delete Internal.List;
                break;
            case Class::Object:
                delete Internal.Map;
                break;
            case Class::String:
                delete Internal.String;
                break;
            default:;
            }
        }

        template <typename T>
        JSON( T b, typename enable_if<is_same<T,bool>::value>::type* = 0 ) : Internal( b ), Type( Class::Boolean ){}

        template <typename T>
        JSON( T i, typename enable_if<is_integral<T>::value && !is_same<T,bool>::value>::type* = 0 ) : Internal( (long)i ), Type( Class::Integral ){}

        template <typename T>
        JSON( T f, typename enable_if<is_floating_point<T>::value>::type* = 0 ) : Internal( (double)f ), Type( Class::Floating ){}

        template <typename T>
        JSON( T s, typename enable_if<is_convertible<T,string>::value>::type* = 0 ) : Internal( string( s ) ), Type( Class::String ){}

        JSON( std::nullptr_t ) : Internal(), Type( Class::Null ){}

        static JSON Make( Class type ) {
            JSON ret; ret.SetType( type );
            return ret;
        }

        static JSON Load( const string & );

        template <typename T>
        void append( T arg ) {
            CheckType( Class::Array ); Internal.List->emplace_back( arg );
        }

        template <typename T, typename... U>
        void append( T arg, U... args ) {
            append( arg ); append( args... );
        }

        template <typename T>
            typename enable_if<is_same<T,bool>::value, JSON&>::type operator=( T b ) {
                CheckType( Class::Boolean ); Internal.Bool = b; return *this;
            }

        template <typename T>
            typename enable_if<is_integral<T>::value && !is_same<T,bool>::value, JSON&>::type operator=( T i ) {
                CheckType( Class::Integral ); Internal.Int = i; return *this;
            }

        template <typename T>
            typename enable_if<is_floating_point<T>::value, JSON&>::type operator=( T f ) {
                CheckType( Class::Floating ); Internal.Float = f; return *this;
            }

        template <typename T>
            typename enable_if<is_convertible<T,string>::value, JSON&>::type operator=( T s ) {
                CheckType( Class::String ); *Internal.String = string( s ); return *this;
            }

        JSON& operator[]( const string &key ) {
            CheckType( Class::Object ); return Internal.Map->operator[]( key );
        }

        JSON& operator[]( size_t index ) {
            CheckType( Class::Array );
            if( index >= Internal.List->size() ) {
                colorful::printHONG( "JSON::operator[]: index out of bounds, use append()" );
                cpptrace::generate_trace().print();
                std::abort();
            };
            return Internal.List->operator[]( index );
        }


        const JSON &at( const string &key ) const {
            CheckType( Class::Object );
            return Internal.Map->at( key );
        }

        const JSON &at( unsigned index ) const {
            CheckType( Class::Array );
            return Internal.List->at( index );
        }

        bool hasKey( const string &key ) const {
            if( Type == Class::Object )
                return Internal.Map->find( key ) != Internal.Map->end();
            colorful::printHONG( "JSON::hasKey(): not an object" );
            cpptrace::generate_trace().print();
            std::abort();
        }
        bool hasKey( const string &key, Class type ) const {
            if( Type == Class::Object ) {
                auto pos = Internal.Map->find( key );
                return pos != Internal.Map->end() && pos->second.JSONType() == type;
            }
            colorful::printHONG( "JSON::hasKey(): not an object" );
            cpptrace::generate_trace().print();
            std::abort();
        }
        bool hasKey_checkTypeIfExist( const string &key, Class type ) const {
            if( Type == Class::Object ) {
                auto pos = Internal.Map->find( key );
                if (pos != Internal.Map->end()) {
                    if (pos->second.JSONType() == type) {
                        return true;
                    } else {
                        colorful::printHONG( "JSON::checkKey(): key type mismatch" );
                        cpptrace::generate_trace().print();
                        std::abort();
                    }
                    return false;
                }
            }
            colorful::printHONG( "JSON::hasKey(): not an object" );
            cpptrace::generate_trace().print();
            std::abort();
        }

        size_t size() const {
            if( Type == Class::Object ) {return Internal.Map->size();}
            else if( Type == Class::Array ) {return Internal.List->size();}
            else {
                colorful::printHONG( "JSON::size(): invalid type" );
                cpptrace::generate_trace().print();
                std::abort();
            }
        }

        Class JSONType() const { return Type; }

        /// Functions for getting primitives from the JSON object.
        bool IsNull() const { return Type == Class::Null; }
        bool IsString() const { return Type == Class::String; }
        bool IsIntegral() const { return Type == Class::Integral; }
        bool IsFloating() const { return Type == Class::Floating; }
        bool IsBoolean() const { return Type == Class::Boolean; }
        bool IsObject() const { return Type == Class::Object; }
        bool IsArray() const { return Type == Class::Array; }

        string ToString() const {
            bool ok = (Type == Class::String);
            if( !ok ) {
                colorful::printHONG( "JSON::ToString(): not a string" );
                cpptrace::generate_trace().print();
                std::abort();
            }
            return json_escape( *Internal.String );
        }

        double ToFloat() const {
            bool ok = (Type == Class::Floating);
            if( !ok ) {
                colorful::printHONG( "JSON::ToFloat(): not a floating point number" );
                cpptrace::generate_trace().print();
                std::abort();
            }
            return Internal.Float;
        }

        long ToInt() const {
            bool ok = (Type == Class::Integral);
            if( !ok ) {
                colorful::printHONG( "JSON::ToInt(): not an integral number" );
                cpptrace::generate_trace().print();
                std::abort();
            }
            return Internal.Int;
        }

        bool ToBool() const {
            bool ok = (Type == Class::Boolean);
            if( !ok ) {
                colorful::printHONG( "JSON::ToBool(): not a boolean" );
                cpptrace::generate_trace().print();
                std::abort();
            }
            return Internal.Bool;
        }

        JSONWrapper<map<string,JSON>> ObjectRange() {
            if( Type == Class::Object )
                return JSONWrapper<map<string,JSON>>( Internal.Map );
            colorful::printHONG( "JSON::ObjectRange(): not an object" );
            cpptrace::generate_trace().print();
            std::abort();
        }

        JSONWrapper<deque<JSON>> ArrayRange() {
            if( Type == Class::Array )
                return JSONWrapper<deque<JSON>>( Internal.List );
            colorful::printHONG( "JSON::ArrayRange(): not an array" );
            cpptrace::generate_trace().print();
            std::abort();
        }

        JSONConstWrapper<map<string,JSON>> ObjectRange() const {
            if( Type == Class::Object )
                return JSONConstWrapper<map<string,JSON>>( Internal.Map );
            colorful::printHONG( "JSON::ObjectRange(): not an object" );
            cpptrace::generate_trace().print();
            std::abort();
        }


        JSONConstWrapper<deque<JSON>> ArrayRange() const { 
            if( Type == Class::Array )
                return JSONConstWrapper<deque<JSON>>( Internal.List );
            colorful::printHONG( "JSON::ArrayRange(): not an array" );
            cpptrace::generate_trace().print();
            std::abort();
        }

        string dump( int depth = 1, string tab = "  ", string next_line = "\n" ) const {
            string pad = "";
            for( int i = 0; i < depth; ++i, pad += tab );

            switch( Type ) {
                case Class::Null:
                    return "null";
                case Class::Object: {
                    string s = "{" + next_line;
                    bool skip = true;
                    for( auto &p : *Internal.Map ) {
                        if( !skip ) s += "," + next_line;
                        s += ( pad + "\"" + p.first + "\" : " + p.second.dump( depth + 1, tab, next_line ) );
                        skip = false;
                    }
                    s += ( next_line + pad.erase( 0, tab.size() ) + "}" ) ;
                    return s;
                }
                case Class::Array: {
                    string s = "[";
                    bool skip = true;
                    for( auto &p : *Internal.List ) {
                        if( !skip ) s += ", ";
                        s += p.dump( depth + 1, tab );
                        skip = false;
                    }
                    s += "]";
                    return s;
                }
                case Class::String:
                    return "\"" + json_escape( *Internal.String ) + "\"";
                case Class::Floating:
                    return std::to_string( Internal.Float );
                case Class::Integral:
                    return std::to_string( Internal.Int );
                case Class::Boolean:
                    return Internal.Bool ? "true" : "false";
                default:
                    return "";
            }
            // return "";
        }

        friend std::ostream& operator<<( std::ostream&, const JSON & );

    private:
        void SetType( Class type ) {
            if( type == Type )
                return;

            ClearInternal();
          
            switch( type ) {
            case Class::Null:      Internal.Map    = nullptr;                break;
            case Class::Object:    Internal.Map    = new map<string,JSON>(); break;
            case Class::Array:     Internal.List   = new deque<JSON>();     break;
            case Class::String:    Internal.String = new string();           break;
            case Class::Floating:  Internal.Float  = 0.0;                    break;
            case Class::Integral:  Internal.Int    = 0;                      break;
            case Class::Boolean:   Internal.Bool   = false;                  break;
            }

            Type = type;
        }


        void CheckType( Class type ) const {
            if( type == Type )
            {
                return;
            }
            else
            {
                colorful::printHONG( "JSON::CheckType: Type mismatch. incoming type %s, this type %s.\n", ClassString(type).c_str(), ClassString(Type).c_str() );
                cpptrace::generate_trace().print();
                std::abort();
            }

        }


    private:
      /* beware: only call if YOU know that Internal is allocated. No checks performed here. 
         This function should be called in a constructed JSON just before you are going to 
        overwrite Internal... 
      */
      void ClearInternal() {
        switch( Type ) {
          case Class::Object: delete Internal.Map;    break;
          case Class::Array:  delete Internal.List;   break;
          case Class::String: delete Internal.String; break;
          default:;
        }
      }

    private:

        Class Type = Class::Null;
};

inline JSON Array() {
    return JSON::Make( JSON::Class::Array );
}

template <typename... T>
JSON Array( T... args ) {
    JSON arr = JSON::Make( JSON::Class::Array );
    arr.append( args... );
    return arr;
}

inline JSON Object() {
    return JSON::Make( JSON::Class::Object );
}

inline JSON String( const string &str ) {
    auto res = JSON::Make( JSON::Class::String);
    res = str;
    return res;
}

inline JSON Float( double f ) {
    auto res = JSON::Make( JSON::Class::Floating);
    res = f;
    return res;
}

inline JSON Integral( int i ) {
    auto res = JSON::Make( JSON::Class::Integral);
    res = i;
    return res;
}

inline JSON Boolean( bool b ) {
    auto res = JSON::Make( JSON::Class::Boolean);
    res = b;
    return res;
}

inline JSON Null() {
    return JSON::Make( JSON::Class::Null);
}

inline std::ostream& operator<<( std::ostream &os, const JSON &json ) {
    os << json.dump();
    return os;
}

namespace {
    inline JSON parse_next( const string &, size_t & );

    inline void consume_ws( const string &str, size_t &offset ) {
        while( isspace( str[offset] ) ) ++offset;
    }

    inline JSON parse_object( const string &str, size_t &offset ) {
        JSON Object = JSON::Make( JSON::Class::Object );

        ++offset;
        consume_ws( str, offset );
        if( str[offset] == '}' ) {
            ++offset; return Object;
        }

        while( true ) {
            JSON Key = parse_next( str, offset );
            consume_ws( str, offset );
            if( str[offset] != ':' ) {
                std::cerr << "Error: Object: Expected colon, found '" << str[offset] << "'\n";
                break;
            }
            consume_ws( str, ++offset );
            JSON Value = parse_next( str, offset );
            Object[Key.ToString()] = Value;
            
            consume_ws( str, offset );
            if( str[offset] == ',' ) {
                ++offset; continue;
            }
            else if( str[offset] == '}' ) {
                ++offset; break;
            }
            else {
                std::cerr << "ERROR: Object: Expected comma, found '" << str[offset] << "'\n";
                break;
            }
        }

        return Object;
    }

    inline JSON parse_array( const string &str, size_t &offset ) {
        JSON Array = JSON::Make( JSON::Class::Array );
        // unsigned index = 0;
        
        ++offset;
        consume_ws( str, offset );
        if( str[offset] == ']' ) {
            ++offset; return Array;
        }

        while( true ) {
            Array.append( parse_next( str, offset ) );
            consume_ws( str, offset );

            if( str[offset] == ',' ) {
                ++offset; continue;
            }
            else if( str[offset] == ']' ) {
                ++offset; break;
            }
            else {
                std::cerr << "ERROR: Array: Expected ',' or ']', found '" << str[offset] << "'\n";
                return JSON::Make( JSON::Class::Array );
            }
        }

        return Array;
    }

    inline JSON parse_string( const string &str, size_t &offset ) {
        JSON String = JSON::Make( JSON::Class::String );
        string val;
        for( char c = str[++offset]; c != '\"' ; c = str[++offset] ) {
            if( c == '\\' ) {
                switch( str[ ++offset ] ) {
                case '\"': val += '\"'; break;
                case '\\': val += '\\'; break;
                case '/' : val += '/' ; break;
                case 'b' : val += '\b'; break;
                case 'f' : val += '\f'; break;
                case 'n' : val += '\n'; break;
                case 'r' : val += '\r'; break;
                case 't' : val += '\t'; break;
                case 'u' : {
                    val += "\\u" ;
                    for( unsigned i = 1; i <= 4; ++i ) {
                        c = str[offset+i];
                        if( (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F') )
                            val += c;
                        else {
                            std::cerr << "ERROR: String: Expected hex character in unicode escape, found '" << c << "'\n";
                            return JSON::Make( JSON::Class::String );
                        }
                    }
                    offset += 4;
                } break;
                default  : val += '\\'; break;
                }
            }
            else
                val += c;
        }
        ++offset;
        String = val;
        return String;
    }

    inline JSON parse_number( const string &str, size_t &offset ) {
        JSON Number;
        string val, exp_str;
        char c;
        bool isDouble = false;
        long exp = 0;
        while( true ) {
            c = str[offset++];
            if( (c == '-') || (c >= '0' && c <= '9') )
                val += c;
            else if( c == '.' ) {
                val += c; 
                isDouble = true;
            }
            else
                break;
        }
        if( c == 'E' || c == 'e' ) {
            c = str[ offset++ ];
            if( c == '-' ){ ++offset; exp_str += '-';}
            while( true ) {
                c = str[ offset++ ];
                if( c >= '0' && c <= '9' )
                    exp_str += c;
                else if( !isspace( c ) && c != ',' && c != ']' && c != '}' ) {
                    std::cerr << "ERROR: Number: Expected a number for exponent, found '" << c << "'\n";
                    cpptrace::generate_trace().print();
                    std::abort();
                    return JSON::Make( JSON::Class::Null );
                }
                else
                    break;
            }
            exp = std::stol( exp_str );
        }
        else if( !isspace( c ) && c != ',' && c != ']' && c != '}' ) {
            std::cerr << "ERROR: Number: unexpected character '" << c << "'\n";
            cpptrace::generate_trace().print();
            std::abort();
            return JSON::Make( JSON::Class::Null );
        }
        --offset;
        
        if( isDouble ) {
            Number = json::Float(std::stod( val ) * std::pow( 10, exp ));
        }
        else {
            if( !exp_str.empty() )
                Number = json::Integral(static_cast<long>(std::stol( val ) * std::pow( 10, exp )));
            else
                Number = json::Integral(static_cast<long>(std::stol( val )));
        }
        return Number;
    }

    inline JSON parse_bool( const string &str, size_t &offset ) {
        JSON Bool = JSON::Make( JSON::Class::Boolean );
        if( str.substr( offset, 4 ) == "true" )
            Bool = true;
        else if( str.substr( offset, 5 ) == "false" )
            Bool = false;
        else {
            std::cerr << "ERROR: Bool: Expected 'true' or 'false', found '" << str.substr( offset, 5 ) << "'\n";
            return JSON::Make( JSON::Class::Null );
        }
        offset += (Bool.ToBool() ? 4 : 5);
        return Bool;
    }

    inline JSON parse_null( const string &str, size_t &offset ) {
        JSON Null = JSON::Make( JSON::Class::Null );
        if( str.substr( offset, 4 ) != "null" ) {
            std::cerr << "ERROR: Null: Expected 'null', found '" << str.substr( offset, 4 ) << "'\n";
            return JSON::Make( JSON::Class::Null );
        }
        offset += 4;
        return Null;
    }

    inline JSON parse_next( const string &str, size_t &offset ) {
        char value;
        consume_ws( str, offset );
        value = str[offset];
        switch( value ) {
            case '[' : return parse_array( str, offset );
            case '{' : return parse_object( str, offset );
            case '\"': return parse_string( str, offset );
            case 't' :
            case 'f' : return parse_bool( str, offset );
            case 'n' : return parse_null( str, offset );
            default  : if( ( value <= '9' && value >= '0' ) || value == '-' )
                           return parse_number( str, offset );
        }
        std::cerr << "ERROR: Parse: Unknown starting character '" << value << "'\n";
        return JSON();
    }
}

inline JSON JSON::Load( const string &str ) {
    size_t offset = 0;
    return parse_next( str, offset );
}

} // End Namespace json
